import logging
from collections.abc import Iterable
from pathlib import Path

from voice.acknowledgment import (
    AcknowledgmentContext,
    AcknowledgmentStrategy,
    PrerenderedAcknowledgment,
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
from voice.conversation import (
    ConversationAudioMixer,
    ConversationAudioRecorder,
    ConversationHistory,
)
from voice.echo_cancellation import (
    EchoCancellationSettings,
    wrap_with_echo_cancellation,
)
from voice.events import SessionEnded, SessionStarted
from voice.events.bus import EventBus
from voice.events.listener import LoggingListener, TranscriptListener
from voice.events.models import VoiceResourcesClosing
from voice.handler import (
    AcknowledgmentHandler,
    BargeInHandler,
    CommandBridge,
    FollowUpHandler,
    FollowUpSettings,
    SpeechResourceHandler,
    TurnCoordinator,
    TurnListener,
    WakeWordHandler,
)
from voice.llm import AgentBridge, AgentSession
from voice.models import AgentResult
from voice.observer import Observer, _ObserverBridge
from voice.stt import CartesiaSpeechToText, SpeechToText, SpeechToTextBridge
from voice.tts import CartesiaTextToSpeech, TextToSpeech, TextToSpeechBridge
from voice.wakeword import WakeWordListener, WakeWordSettings

logger = logging.getLogger(__name__)


class VoiceAgent:
    """Owns and wires one wake-word-driven voice session."""

    def __init__(
        self,
        *,
        agent_session: AgentSession,
        audio_input: AudioInput | None = None,
        audio_output: AudioOutput | None = None,
        wake_word_settings: WakeWordSettings | None = None,
        barge_in: BargeInStrategy | None = None,
        acknowledgment: AcknowledgmentStrategy | None = None,
        echo_cancellation_settings: EchoCancellationSettings | None = None,
        speech_to_text: SpeechToText | None = None,
        text_to_speech: TextToSpeech | None = None,
        follow_up_settings: FollowUpSettings | None = None,
        observers: Iterable[Observer] = (),
        recording_path: str | Path | None = None,
    ) -> None:
        self._event_bus = EventBus()
        self._conversation_history = ConversationHistory()
        self._recording_path = Path(recording_path) if recording_path else None
        self._audio_session = (
            PortAudioSession() if audio_input is None or audio_output is None else None
        )

        physical_input = audio_input or MicrophoneAudioInput(
            session=self._audio_session
        )
        physical_output = audio_output or LocalAudioOutput(session=self._audio_session)
        echo_cancelled_input, echo_referenced_output = wrap_with_echo_cancellation(
            physical_input,
            physical_output,
            settings=echo_cancellation_settings or EchoCancellationSettings(),
        )

        self._buffered_audio_input = BufferedAudioInput(echo_cancelled_input)
        self._user_audio_producer = UserAudioProducer(
            event_bus=self._event_bus,
            buffered_audio_input=self._buffered_audio_input,
        )
        self._audio_bridge = AudioBridge(
            event_bus=self._event_bus,
            output_device=echo_referenced_output,
        )
        self._speech_to_text = speech_to_text or CartesiaSpeechToText(
            sample_rate=self._buffered_audio_input.sample_rate
        )
        self._text_to_speech = text_to_speech or CartesiaTextToSpeech()
        wake_word_settings = wake_word_settings or WakeWordSettings()
        self._wake_word = WakeWordListener(
            buffered_audio_input=self._buffered_audio_input,
            settings=wake_word_settings,
        )
        self._setup_handlers(
            agent_session,
            barge_in,
            acknowledgment,
            strip_wake_word=wake_word_settings.strip_from_command,
            follow_up_settings=follow_up_settings,
        )
        self._stopped = False
        self._setup_observers(
            observers,
            self._recording_path,
            wake_word_phrase=self._wake_word.phrase,
        )

    def _setup_handlers(
        self,
        agent_session: AgentSession,
        barge_in: BargeInStrategy | None,
        acknowledgment: AcknowledgmentStrategy | None,
        *,
        strip_wake_word: bool,
        follow_up_settings: FollowUpSettings | None,
    ) -> None:
        self._agent_bridge = AgentBridge(
            event_bus=self._event_bus,
            session=agent_session,
        )
        self._text_to_speech_bridge = TextToSpeechBridge(
            event_bus=self._event_bus,
            text_to_speech=self._text_to_speech,
        )
        self._speech_to_text_bridge = SpeechToTextBridge(
            event_bus=self._event_bus,
            buffered_audio_input=self._buffered_audio_input,
            speech_to_text=self._speech_to_text,
        )
        self._command_bridge = CommandBridge(
            event_bus=self._event_bus,
            wake_word_phrase=self._wake_word.phrase,
            strip_wake_word=strip_wake_word,
        )
        self._turn_coordinator = TurnCoordinator()
        self._turn_listener = TurnListener(
            event_bus=self._event_bus,
            coordinator=self._turn_coordinator,
        )
        self._wake_word_handler = WakeWordHandler(
            event_bus=self._event_bus,
            source=self._wake_word,
        )
        strategy = barge_in or WakeWordBargeIn()
        strategy.set_context(
            BargeInContext(
                event_bus=self._event_bus,
                audio_format=self._buffered_audio_input.format,
            )
        )
        self._barge_in_handler = BargeInHandler(
            event_bus=self._event_bus,
            strategy=strategy,
            coordinator=self._turn_coordinator,
        )
        acknowledgment_strategy = acknowledgment or PrerenderedAcknowledgment()
        acknowledgment_strategy.set_context(
            AcknowledgmentContext(event_bus=self._event_bus)
        )
        self._acknowledgment_handler = AcknowledgmentHandler(
            event_bus=self._event_bus,
            strategy=acknowledgment_strategy,
        )
        self._follow_up_handler = FollowUpHandler(
            event_bus=self._event_bus,
            settings=follow_up_settings,
        )
        self._speech_resource_handler = SpeechResourceHandler(
            event_bus=self._event_bus,
            speech_to_text=self._speech_to_text,
            text_to_speech=self._text_to_speech,
        )

    def _setup_observers(
        self,
        observers: Iterable[Observer],
        recording_path: str | Path | None,
        *,
        wake_word_phrase: str,
    ) -> None:
        self._logging_listener = LoggingListener(
            self._event_bus, wake_word_phrase=wake_word_phrase
        )
        self._transcript_listener = TranscriptListener(
            self._event_bus, self._conversation_history
        )
        self._observer_bridge = _ObserverBridge(
            event_bus=self._event_bus,
            observers=observers,
        )
        self._observer_bridge.setup()
        if recording_path is not None:
            self._audio_recorder = ConversationAudioRecorder(
                self._event_bus,
                ConversationAudioMixer(
                    recording_path,
                    user_sample_rate=self._buffered_audio_input.sample_rate,
                ),
            )

    async def start(self) -> AgentResult:
        if self._stopped:
            raise RuntimeError("Voice agent is stopped.")

        try:
            await self._observer_bridge.prepare()
            started = await self._event_bus.dispatch(SessionStarted())
            started.raise_if_failed()
            logger.debug("Session started")
            await self._wake_word_handler.run()
        finally:
            await self.stop()
        return AgentResult(
            recording_path=self._recording_path,
            conversation_history=self._conversation_history.turns,
        )

    async def stop(self) -> None:
        if self._stopped:
            return
        self._stopped = True

        logger.debug("Session ending, closing voice resources")
        await self._event_bus.dispatch(SessionEnded())
        await self._event_bus.dispatch(VoiceResourcesClosing())
        if self._audio_session is not None:
            self._audio_session.close()
