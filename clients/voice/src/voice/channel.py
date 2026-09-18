import asyncio
from collections.abc import Iterable

from voice.activation import (
    ActivationCoordinator,
    ActivationSource,
    WakeWordActivationSource,
)
from voice.audio import (
    AudioBridge,
    AudioInput,
    AudioOutput,
    BufferedAudioInput,
    UserAudioProducer,
)
from voice.barge_in import BargeInContext, BargeInStrategy, WakeWordBargeIn
from voice.echo_cancellation import (
    EchoCancellationSettings,
    EchoPresence,
    wrap_with_echo_cancellation,
)
from voice.events import AssistantTurnStarted, SessionEnded, SessionStarted
from voice.events.bus import EventBus
from voice.events.listener import EventTrace, LoggingListener
from voice.events.models import VoiceResourcesClosing, VoiceTurnEnded
from voice.gateway import GatewayVoiceBridge, GatewayVoiceSession
from voice.integration import VoiceIntegration, VoiceIntegrationBridge
from voice.wakeword import WakeWordListener, WakeWordSettings


class VoiceChannel:
    """Connects local audio hardware to a gateway-owned voice session."""

    def __init__(
        self,
        *,
        gateway_session: GatewayVoiceSession,
        audio_input: AudioInput,
        audio_output: AudioOutput,
        wake_word_settings: WakeWordSettings | None = None,
        wake_word_enabled: bool = True,
        barge_in: BargeInStrategy | None = None,
        echo_cancellation_settings: EchoCancellationSettings | None = None,
        echo_cancellation_enabled: bool = True,
        activation_sources: Iterable[ActivationSource] = (),
        integrations: Iterable[VoiceIntegration] = (),
    ) -> None:
        self._gateway_session = gateway_session
        self._event_bus = EventBus()
        echo_settings = echo_cancellation_settings or EchoCancellationSettings()
        if echo_cancellation_enabled:
            channel_input, channel_output, echo_presence = wrap_with_echo_cancellation(
                audio_input,
                audio_output,
                settings=echo_settings,
            )
        else:
            channel_input = audio_input
            channel_output = audio_output
            echo_presence = _NoEchoPresence()
        self._buffered_audio_input = BufferedAudioInput(
            channel_input,
            echo_presence=echo_presence,
        )
        if self._buffered_audio_input.sample_rate != gateway_session.input_sample_rate:
            raise ValueError(
                "Audio input sample rate does not match the negotiated gateway format"
            )
        self._user_audio_producer = UserAudioProducer(
            event_bus=self._event_bus,
            buffered_audio_input=self._buffered_audio_input,
        )
        self._audio_bridge = AudioBridge(
            event_bus=self._event_bus,
            output_device=channel_output,
        )
        self._event_trace = EventTrace(self._event_bus)
        self._logging_listener: LoggingListener | None = None
        sources = list(activation_sources)
        if wake_word_enabled:
            settings = wake_word_settings or WakeWordSettings()
            wake_word = WakeWordListener(
                buffered_audio_input=self._buffered_audio_input,
                settings=settings,
            )
            wake_word_source = WakeWordActivationSource(
                event_bus=self._event_bus,
                listener=wake_word,
            )
            sources.insert(0, wake_word_source)
            self._logging_listener = LoggingListener(
                self._event_bus,
                wake_word_phrase=settings.wake_word.label.replace("_", " "),
            )
        self._gateway_bridge = GatewayVoiceBridge(
            self._event_bus,
            gateway_session,
            self._buffered_audio_input,
            max_echo_confidence=echo_settings.max_upload_echo_confidence,
        )
        self._activation_coordinator = ActivationCoordinator(
            event_bus=self._event_bus,
            sources=sources,
        )
        self._barge_in = barge_in or WakeWordBargeIn()
        self._assistant_responding = False
        self._event_bus.on(AssistantTurnStarted, self._on_assistant_turn_started)
        self._event_bus.on(VoiceTurnEnded, self._on_voice_turn_ended)
        self._barge_in.set_context(
            BargeInContext(
                event_bus=self._event_bus,
                audio_format=self._buffered_audio_input.format,
                echo_presence=echo_presence,
            )
        )
        self._integration_bridge = VoiceIntegrationBridge(
            event_bus=self._event_bus,
            integrations=integrations,
        )
        self._integration_bridge.setup()
        self._stopped = False

    async def start(self) -> None:
        if self._stopped:
            raise RuntimeError("Voice channel is stopped")
        try:
            await self._integration_bridge.prepare()
            await self._gateway_bridge.start()
            await self._event_bus.emit(SessionStarted())
            activation = asyncio.create_task(
                self._activation_coordinator.run(),
                name="voice-activation-coordinator",
            )
            barge_in = asyncio.create_task(
                self._watch_barge_in(),
                name="voice-barge-in",
            )
            done, pending = await asyncio.wait(
                (activation, barge_in),
                return_when=asyncio.FIRST_COMPLETED,
            )
            for task in pending:
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)
            for task in done:
                task.result()
        finally:
            await self.stop()

    async def stop(self) -> None:
        if self._stopped:
            return
        self._stopped = True
        await self._event_bus.emit(SessionEnded())
        await self._event_bus.emit(VoiceResourcesClosing())
        await self._gateway_session.close()

    async def _watch_barge_in(self) -> None:
        async for signal in self._barge_in.signals():
            # Only the assistant's response can be barged into; while the user
            # is still speaking their command, speech is the turn itself.
            if not self._assistant_responding:
                continue
            self._assistant_responding = False
            await self._gateway_bridge.interrupt(signal.sequence)

    async def _on_assistant_turn_started(self, _: AssistantTurnStarted) -> None:
        self._assistant_responding = True

    async def _on_voice_turn_ended(self, _: VoiceTurnEnded) -> None:
        self._assistant_responding = False


class _NoEchoPresence(EchoPresence):
    @property
    def echo_confidence(self) -> float:
        return 0.0
