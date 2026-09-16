import asyncio
from collections.abc import Iterable
from pathlib import Path

from voice.acknowledgement import ToolAcknowledgementObserver
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
from voice.audio.input import MicrophoneAudioInput
from voice.audio.output import LocalAudioOutput
from voice.audio.session import PortAudioSession
from voice.barge_in import BargeInContext, BargeInStrategy, WakeWordBargeIn
from voice.conversation import ConversationAudioMixer, ConversationAudioRecorder
from voice.echo_cancellation import (
    EchoCancellationSettings,
    wrap_with_echo_cancellation,
)
from voice.events import AssistantTurnStarted, SessionEnded, SessionStarted
from voice.events.bus import EventBus
from voice.events.models import VoiceResourcesClosing, VoiceTurnEnded
from voice.gateway import GatewayVoiceBridge, GatewayVoiceSession
from voice.handler import FollowUpHandler, FollowUpSettings
from voice.models import AgentResult
from voice.observer import Observer, ObserverBridge
from voice.wakeword import WakeWordListener, WakeWordSettings


class VoiceChannel:
    """Connects local audio hardware to a gateway-owned voice session."""

    def __init__(
        self,
        *,
        gateway_session: GatewayVoiceSession,
        audio_input: AudioInput | None = None,
        audio_output: AudioOutput | None = None,
        wake_word_settings: WakeWordSettings | None = None,
        barge_in: BargeInStrategy | None = None,
        echo_cancellation_settings: EchoCancellationSettings | None = None,
        follow_up_settings: FollowUpSettings | None = None,
        activation_sources: Iterable[ActivationSource] = (),
        observers: Iterable[Observer] = (),
        recording_path: str | Path | None = None,
    ) -> None:
        self._gateway_session = gateway_session
        self._event_bus = EventBus()
        self._recording_path = Path(recording_path) if recording_path else None
        self._audio_session = (
            PortAudioSession() if audio_input is None or audio_output is None else None
        )
        physical_input = audio_input or MicrophoneAudioInput(
            session=self._audio_session
        )
        physical_output = audio_output or LocalAudioOutput(session=self._audio_session)
        echo_cancelled_input, echo_referenced_output, echo_presence = (
            wrap_with_echo_cancellation(
                physical_input,
                physical_output,
                settings=echo_cancellation_settings or EchoCancellationSettings(),
            )
        )
        self._buffered_audio_input = BufferedAudioInput(echo_cancelled_input)
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
            output_device=echo_referenced_output,
        )
        wake_word_settings = wake_word_settings or WakeWordSettings()
        self._wake_word = WakeWordListener(
            buffered_audio_input=self._buffered_audio_input,
            settings=wake_word_settings,
        )
        self._gateway_bridge = GatewayVoiceBridge(
            self._event_bus,
            gateway_session,
            self._buffered_audio_input,
        )
        self._activation_coordinator = ActivationCoordinator(
            event_bus=self._event_bus,
            sources=(
                WakeWordActivationSource(
                    event_bus=self._event_bus,
                    listener=self._wake_word,
                ),
                *activation_sources,
            ),
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
        self._follow_up = FollowUpHandler(
            event_bus=self._event_bus,
            settings=follow_up_settings,
        )
        self._observer_bridge = ObserverBridge(
            event_bus=self._event_bus,
            observers=(*observers, ToolAcknowledgementObserver()),
        )
        self._observer_bridge.setup()
        self._audio_recorder: ConversationAudioRecorder | None = None
        if self._recording_path is not None:
            self._audio_recorder = ConversationAudioRecorder(
                self._event_bus,
                ConversationAudioMixer(
                    self._recording_path,
                    user_sample_rate=self._buffered_audio_input.sample_rate,
                    assistant_sample_rate=gateway_session.output_sample_rate,
                ),
            )
        self._stopped = False

    async def start(self) -> AgentResult:
        if self._stopped:
            raise RuntimeError("Voice channel is stopped")
        try:
            await self._observer_bridge.prepare()
            await self._gateway_bridge.start()
            started = await self._event_bus.dispatch(SessionStarted())
            started.raise_if_failed()
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
        return AgentResult(recording_path=self._recording_path)

    async def stop(self) -> None:
        if self._stopped:
            return
        self._stopped = True
        await self._event_bus.dispatch(SessionEnded())
        await self._event_bus.dispatch(VoiceResourcesClosing())
        await self._gateway_session.close()
        if self._audio_session is not None:
            self._audio_session.close()

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
