from collections.abc import Iterable
from contextlib import AsyncExitStack
from types import TracebackType
from typing import Self

from sonosify import SonosClient

from voice.acknowledgement import ToolAcknowledgementIntegration
from voice.activation import ActivationSource
from voice.audio import AudioOutput
from voice.audio.output.sonos import SonosOutput
from voice.barge_in import BargeInStrategy, NoBargeIn, SpeechBargeIn, WakeWordBargeIn
from voice.channel import VoiceChannel
from voice.config import (
    AudioOutputType,
    BargeInType,
    SonosAudioFocusStrategy,
    VoiceClientConfig,
)
from voice.echo_cancellation import EchoCancellationSettings
from voice.gateway import GatewayVoiceSession
from voice.handler import FollowUpSettings
from voice.integration import VoiceIntegration
from voice.lights import HueIntegration
from voice.playback import (
    SonosAudioFocusIntegration,
    SonosDuckingPolicy,
    SonosPausePolicy,
)
from voice.sonos import SonosSettings
from voice.sound import SoundIntegration
from voice.wakeword import WakeWord, WakeWordSettings


class VoiceClient:
    """Builds and owns a complete voice channel from validated configuration."""

    def __init__(
        self,
        config: VoiceClientConfig,
        *,
        activation_sources: Iterable[ActivationSource] = (),
        integrations: Iterable[VoiceIntegration] = (),
    ) -> None:
        self._config = config
        self._activation_sources = tuple(activation_sources)
        self._additional_integrations = tuple(integrations)
        self._resources: AsyncExitStack | None = None
        self._channel: VoiceChannel | None = None

    async def __aenter__(self) -> Self:
        if self._resources is not None:
            raise RuntimeError("Voice client is already running.")

        resources = AsyncExitStack()
        await resources.__aenter__()
        try:
            gateway_session = await self._connect_gateway()
            await resources.enter_async_context(gateway_session)
            sonos_client = await self._open_sonos(resources)
            audio_output = self._build_audio_output(sonos_client)
            integrations = self._build_integrations(sonos_client)
            self._channel = VoiceChannel(
                gateway_session=gateway_session,
                audio_output=audio_output,
                wake_word_settings=self._build_wake_word_settings(),
                wake_word_enabled=self._config.activation.wake_word.enabled,
                barge_in=self._build_barge_in(),
                echo_cancellation_settings=self._build_echo_cancellation_settings(),
                echo_cancellation_enabled=(
                    self._config.audio.echo_cancellation.enabled
                ),
                follow_up_settings=self._build_follow_up_settings(),
                follow_up_enabled=self._config.follow_up.enabled,
                activation_sources=self._activation_sources,
                integrations=integrations,
                recording_path=self._recording_path(),
            )
        except BaseException:
            await resources.aclose()
            raise

        self._resources = resources
        return self

    async def __aexit__(
        self,
        _exc_type: type[BaseException] | None,
        _exc_value: BaseException | None,
        _traceback: TracebackType | None,
    ) -> None:
        channel, self._channel = self._channel, None
        resources, self._resources = self._resources, None
        try:
            if channel is not None:
                await channel.stop()
        finally:
            if resources is not None:
                await resources.aclose()

    async def run(self) -> None:
        if self._channel is None:
            raise RuntimeError("Use 'async with VoiceClient(config)' before run().")
        await self._channel.start()

    async def _connect_gateway(self) -> GatewayVoiceSession:
        gateway = self._config.gateway
        session = self._config.session
        return await GatewayVoiceSession.connect(
            gateway.url,
            token=gateway.token,
            device_id=session.client_id,
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

    def _build_audio_output(
        self, sonos_client: SonosClient | None
    ) -> AudioOutput | None:
        if self._config.audio.output.type is AudioOutputType.LOCAL:
            return None
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
        return SonosOutput(client=client, settings=settings)

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
        )

    def _build_follow_up_settings(self) -> FollowUpSettings | None:
        settings = self._config.follow_up
        if not settings.enabled:
            return None
        return FollowUpSettings(
            window_seconds=settings.window_seconds,
            countdown_seconds=settings.countdown_seconds,
        )

    def _recording_path(self) -> str | None:
        settings = self._config.recording
        return str(settings.path) if settings.enabled else None


def _require_sonos_client(client: SonosClient | None) -> SonosClient:
    if client is None:
        raise RuntimeError("The validated configuration did not create a Sonos client.")
    return client
