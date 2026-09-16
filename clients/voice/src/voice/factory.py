from collections.abc import Iterable
from contextlib import AsyncExitStack
from pathlib import Path
from typing import Self

from sonosify import SonosClient

from voice.acknowledgement import ToolAcknowledgementIntegration
from voice.activation import ActivationSource
from voice.audio import AudioInput, AudioOutput, PortAudioSession
from voice.audio.input import MicrophoneAudioInput
from voice.audio.output import LocalAudioOutput
from voice.audio.output.sonos import SonosOutput
from voice.barge_in import BargeInStrategy, NoBargeIn, SpeechBargeIn, WakeWordBargeIn
from voice.channel import VoiceChannel
from voice.config import (
    AudioOutputType,
    BargeInType,
    SonosAudioFocusStrategy,
    VoiceSessionConfig,
)
from voice.echo_cancellation import EchoCancellationSettings
from voice.gateway import GatewayVoiceSession
from voice.integration import VoiceIntegration
from voice.lights import HueIntegration
from voice.playback import (
    SonosAudioFocusIntegration,
    SonosDuckingPolicy,
    SonosPausePolicy,
)
from voice.session import VoiceSession
from voice.sonos import SonosSettings
from voice.sound import SoundIntegration
from voice.wakeword import WakeWord, WakeWordSettings


class VoiceSessionFactory:
    """Creates configured voice sessions and their external resources."""

    def __init__(
        self,
        config: VoiceSessionConfig,
        *,
        activation_sources: Iterable[ActivationSource] = (),
        integrations: Iterable[VoiceIntegration] = (),
    ) -> None:
        self._config = config
        self._activation_sources = tuple(activation_sources)
        self._additional_integrations = tuple(integrations)

    @classmethod
    def from_yaml(
        cls,
        path: str | Path | None = None,
        *,
        activation_sources: Iterable[ActivationSource] = (),
        integrations: Iterable[VoiceIntegration] = (),
    ) -> Self:
        config = (
            VoiceSessionConfig.from_yaml()
            if path is None
            else VoiceSessionConfig.from_yaml(path)
        )
        return cls(
            config,
            activation_sources=activation_sources,
            integrations=integrations,
        )

    async def create(self) -> VoiceSession:
        resources = AsyncExitStack()
        await resources.__aenter__()
        try:
            gateway_session = await self._connect_gateway()
            await resources.enter_async_context(gateway_session)
            sonos_client = await self._open_sonos(resources)
            audio_input, audio_output = self._build_audio_devices(
                sonos_client, resources
            )
            integrations = self._build_integrations(sonos_client)
            channel = VoiceChannel(
                gateway_session=gateway_session,
                audio_input=audio_input,
                audio_output=audio_output,
                wake_word_settings=self._build_wake_word_settings(),
                wake_word_enabled=self._config.activation.wake_word.enabled,
                barge_in=self._build_barge_in(),
                echo_cancellation_settings=self._build_echo_cancellation_settings(),
                echo_cancellation_enabled=(
                    self._config.audio.echo_cancellation.enabled
                ),
                activation_sources=self._activation_sources,
                integrations=integrations,
                recording_path=self._recording_path(),
            )
            return VoiceSession(channel=channel, resources=resources)
        except BaseException:
            await resources.aclose()
            raise

    async def _connect_gateway(self) -> GatewayVoiceSession:
        gateway = self._config.gateway
        session = self._config.session
        return await GatewayVoiceSession.connect(
            gateway.url,
            token=gateway.token,
            room=self._config.room,
            channel=session.channel,
            new_session=session.new_session,
            inactivity_timeout_seconds=session.inactivity_timeout_seconds,
        )

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

    def _build_audio_devices(
        self, sonos_client: SonosClient | None, resources: AsyncExitStack
    ) -> tuple[AudioInput, AudioOutput]:
        if self._config.audio.output.type is not AudioOutputType.LOCAL:
            client = _require_sonos_client(sonos_client)
            sonos = self._config.sonos
            if sonos is None:
                raise RuntimeError("Sonos settings were not validated.")
            settings = SonosSettings(
                ip_address=sonos.ip_address,
                local_host=sonos.local_host,
                clip_volume_boost=sonos.clip_volume_boost,
                clip_prebuffer_seconds=sonos.clip_prebuffer_seconds,
            )
            return MicrophoneAudioInput(), SonosOutput(client=client, settings=settings)
        session = resources.enter_context(PortAudioSession())
        return MicrophoneAudioInput(session=session), LocalAudioOutput(session=session)

    def _build_integrations(
        self, sonos_client: SonosClient | None
    ) -> tuple[VoiceIntegration, ...]:
        settings = self._config.integrations
        integrations = list(self._additional_integrations)
        if settings.sounds.enabled:
            sound = SoundIntegration()
            integrations.append(sound)
        if settings.tool_acknowledgements.enabled:
            acknowledgements = ToolAcknowledgementIntegration()
            integrations.append(acknowledgements)
        if settings.hue.enabled:
            hue = HueIntegration(room_name=settings.hue.room_name)
            integrations.append(hue)
        if settings.sonos_audio_focus.enabled:
            client = _require_sonos_client(sonos_client)
            if settings.sonos_audio_focus.strategy is SonosAudioFocusStrategy.DUCK:
                policy = SonosDuckingPolicy(client=client)
            else:
                policy = SonosPausePolicy(client=client)
            audio_focus = SonosAudioFocusIntegration(policy=policy)
            integrations.append(audio_focus)
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

    def _build_barge_in(self) -> BargeInStrategy:
        settings = self._config.barge_in
        if settings.type is BargeInType.DISABLED:
            return NoBargeIn()
        if settings.type is BargeInType.WAKE_WORD:
            return WakeWordBargeIn()
        return SpeechBargeIn(
            min_level_dbfs=settings.min_level_dbfs,
            min_speech_probability=settings.min_speech_probability,
            min_speech_seconds=settings.min_speech_seconds,
            max_echo_confidence=settings.max_echo_confidence,
        )

    def _build_echo_cancellation_settings(self) -> EchoCancellationSettings | None:
        settings = self._config.audio.echo_cancellation
        if not settings.enabled:
            return None
        return EchoCancellationSettings(
            sample_rate=settings.sample_rate,
            reference_history_seconds=settings.reference_history_seconds,
            max_upload_echo_confidence=settings.max_upload_echo_confidence,
        )

    def _recording_path(self) -> str | None:
        settings = self._config.recording
        return str(settings.path) if settings.enabled else None


def _require_sonos_client(client: SonosClient | None) -> SonosClient:
    if client is None:
        raise RuntimeError("The validated configuration did not create a Sonos client.")
    return client
