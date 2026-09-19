from collections.abc import Iterable
from contextlib import AsyncExitStack
from pathlib import Path

from sonosify import SonosClient

from voice.activation import ActivationSource, WakeWordActivationSource
from voice.adapters.gateway import GatewayVoiceBackendConnector
from voice.audio import (
    AudioDeviceFactory,
    AudioDevices,
    AudioFormat,
    BufferedAudioInput,
    PortAudioSession,
)
from voice.audio.input import MicrophoneAudioInput
from voice.audio.output import LocalAudioOutput
from voice.audio.output.sonos import SonosOutput
from voice.backend import BackendConnectionOptions, VoiceBackend, VoiceBackendConnector
from voice.barge_in import BargeInStrategy, NoBargeIn, SpeechBargeIn, WakeWordBargeIn
from voice.config import (
    AudioOutputType,
    BargeInType,
    SonosAudioFocusStrategy,
    SonosConfig,
    VoiceSessionConfig,
)
from voice.echo_cancellation import (
    EchoCancellationSettings,
    wrap_with_echo_cancellation,
)
from voice.integrations import VoiceIntegration
from voice.integrations.hue import HueIntegration
from voice.integrations.sonos_audio_focus import (
    SonosAudioFocusIntegration,
    SonosDuckingPolicy,
    SonosPausePolicy,
)
from voice.integrations.sounds import SoundIntegration
from voice.lifecycle import VoiceLifecycleObserver
from voice.lifecycle.logging_observer import LoggingObserver
from voice.lifecycle.trace import LifecycleTrace
from voice.runtime import VoiceRuntime
from voice.session import VoiceSession
from voice.sonos import SonosSettings
from voice.wakeword import WakeWord, WakeWordListener, WakeWordSettings

_OUTPUT_FORMAT = AudioFormat(sample_rate=24_000)


class VoiceSessionFactory:
    """Composes voice sessions from configuration and opens their resources.

    The defaults connect to the configured Gateway and use local audio
    hardware; tests and embedders inject their own connector or devices.
    """

    def __init__(
        self,
        config: VoiceSessionConfig,
        *,
        backend_connector: VoiceBackendConnector | None = None,
        audio_devices: AudioDeviceFactory | None = None,
        activation_sources: Iterable[ActivationSource] = (),
        integrations: Iterable[VoiceIntegration] = (),
    ) -> None:
        self._config = config
        self._backend_connector = backend_connector or GatewayVoiceBackendConnector(
            config.gateway.url, token=config.gateway.token
        )
        self._audio_devices = audio_devices
        self._activation_sources = tuple(activation_sources)
        self._additional_integrations = tuple(integrations)

    @classmethod
    async def from_yaml(
        cls,
        path: str | Path | None = None,
        *,
        backend_connector: VoiceBackendConnector | None = None,
        audio_devices: AudioDeviceFactory | None = None,
        activation_sources: Iterable[ActivationSource] = (),
        integrations: Iterable[VoiceIntegration] = (),
    ) -> VoiceSession:
        config = (
            VoiceSessionConfig.from_yaml()
            if path is None
            else VoiceSessionConfig.from_yaml(path)
        )
        factory = cls(
            config,
            backend_connector=backend_connector,
            audio_devices=audio_devices,
            activation_sources=activation_sources,
            integrations=integrations,
        )
        return await factory.create()

    async def create(self) -> VoiceSession:
        resources = AsyncExitStack()
        await resources.__aenter__()
        try:
            sonos_client = await self._open_sonos(resources)
            devices_factory = self._audio_devices or _ConfiguredAudioDevices(
                output_type=self._config.audio.output.type,
                sonos=self._config.sonos,
                sonos_client=sonos_client,
            )
            devices = await devices_factory.open(resources)
            backend = await self._connect_backend(devices, resources)
            runtime = self._build_runtime(backend, devices, sonos_client)
            return VoiceSession(runtime=runtime, resources=resources)
        except BaseException:
            await resources.aclose()
            raise

    async def _open_sonos(self, resources: AsyncExitStack) -> SonosClient | None:
        settings = self._config.sonos
        sonos_enabled = (
            self._config.audio.output.type is AudioOutputType.SONOS
            or self._config.integrations.sonos_audio_focus.enabled
        )
        if settings is None or not sonos_enabled:
            return None
        client = SonosClient(settings.ip_address)
        return await resources.enter_async_context(client)

    async def _connect_backend(
        self, devices: AudioDevices, resources: AsyncExitStack
    ) -> VoiceBackend:
        session = self._config.session
        backend = await self._backend_connector.connect(
            BackendConnectionOptions(
                room=self._config.room,
                channel=session.channel,
                inactivity_timeout_seconds=session.inactivity_timeout_seconds,
                input_format=AudioFormat(
                    sample_rate=devices.input.sample_rate,
                    channels=devices.input.channels,
                ),
                output_format=_OUTPUT_FORMAT,
            )
        )
        resources.push_async_callback(backend.close)
        return backend

    def _build_runtime(
        self,
        backend: VoiceBackend,
        devices: AudioDevices,
        sonos_client: SonosClient | None,
    ) -> VoiceRuntime:
        echo_settings = self._build_echo_cancellation_settings()
        if self._config.audio.echo_cancellation.enabled:
            audio_input, audio_output, echo_presence = wrap_with_echo_cancellation(
                devices.input, devices.output, settings=echo_settings
            )
            buffered_input = BufferedAudioInput(
                audio_input, echo_presence=echo_presence
            )
        else:
            audio_output = devices.output
            buffered_input = BufferedAudioInput(devices.input)

        activation_sources = list(self._activation_sources)
        observers: list[VoiceLifecycleObserver] = [LifecycleTrace()]
        wake_word_settings = self._build_wake_word_settings()
        if wake_word_settings is not None:
            listener = WakeWordListener(buffered_input, settings=wake_word_settings)
            activation_sources.insert(0, WakeWordActivationSource(listener))
            observers.append(LoggingObserver(wake_word_phrase=listener.phrase))

        return VoiceRuntime(
            backend=backend,
            audio_input=buffered_input,
            audio_output=audio_output,
            activation_sources=activation_sources,
            barge_in=self._build_barge_in(buffered_input),
            integrations=self._build_integrations(sonos_client),
            observers=observers,
            max_echo_confidence=echo_settings.max_upload_echo_confidence,
        )

    def _build_integrations(
        self, sonos_client: SonosClient | None
    ) -> tuple[VoiceIntegration, ...]:
        settings = self._config.integrations
        integrations = list(self._additional_integrations)
        if settings.sounds.enabled:
            integrations.append(SoundIntegration())
        if settings.hue.enabled:
            integrations.append(HueIntegration(room_name=settings.hue.room_name))
        if settings.sonos_audio_focus.enabled:
            client = _require_sonos_client(sonos_client)
            if settings.sonos_audio_focus.strategy is SonosAudioFocusStrategy.DUCK:
                policy = SonosDuckingPolicy(client=client)
            else:
                policy = SonosPausePolicy(client=client)
            integrations.append(SonosAudioFocusIntegration(policy=policy))
        return tuple(integrations)

    def _build_wake_word_settings(self) -> WakeWordSettings | None:
        settings = self._config.activation.wake_word
        if not settings.enabled:
            return None
        return WakeWordSettings(
            wake_word=WakeWord(f"{settings.word.value}_v0.1"),
            sensitivity=settings.sensitivity,
            cooldown=settings.cooldown_seconds,
            strip_from_command=settings.strip_from_command,
        )

    def _build_barge_in(self, buffered_input: BufferedAudioInput) -> BargeInStrategy:
        settings = self._config.barge_in
        if settings.type is BargeInType.DISABLED:
            return NoBargeIn()
        if settings.type is BargeInType.WAKE_WORD:
            return WakeWordBargeIn()
        return SpeechBargeIn(
            buffered_input,
            min_level_dbfs=settings.min_level_dbfs,
            min_speech_probability=settings.min_speech_probability,
            min_speech_seconds=settings.min_speech_seconds,
            max_echo_confidence=settings.max_echo_confidence,
        )

    def _build_echo_cancellation_settings(self) -> EchoCancellationSettings:
        settings = self._config.audio.echo_cancellation
        return EchoCancellationSettings(
            sample_rate=settings.sample_rate,
            reference_history_seconds=settings.reference_history_seconds,
            max_upload_echo_confidence=settings.max_upload_echo_confidence,
        )


class _ConfiguredAudioDevices(AudioDeviceFactory):
    def __init__(
        self,
        *,
        output_type: AudioOutputType,
        sonos: SonosConfig | None,
        sonos_client: SonosClient | None,
    ) -> None:
        self._output_type = output_type
        self._sonos = sonos
        self._sonos_client = sonos_client

    async def open(self, resources: AsyncExitStack) -> AudioDevices:
        if self._output_type is AudioOutputType.LOCAL:
            session = resources.enter_context(PortAudioSession())
            return AudioDevices(
                input=MicrophoneAudioInput(session=session),
                output=LocalAudioOutput(session=session),
            )
        client = _require_sonos_client(self._sonos_client)
        if self._sonos is None:
            raise RuntimeError("Sonos settings were not validated.")
        settings = SonosSettings(
            ip_address=self._sonos.ip_address,
            local_host=self._sonos.local_host,
            clip_volume_boost=self._sonos.clip_volume_boost,
            clip_prebuffer_seconds=self._sonos.clip_prebuffer_seconds,
        )
        return AudioDevices(
            input=MicrophoneAudioInput(),
            output=SonosOutput(client=client, settings=settings),
        )


def _require_sonos_client(client: SonosClient | None) -> SonosClient:
    if client is None:
        raise RuntimeError("The validated configuration did not create a Sonos client.")
    return client
