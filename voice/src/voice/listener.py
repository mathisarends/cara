from agent.events import (
    AssistantInterrupted,
    AssistantSpeechStarted,
    SessionEnded,
    SessionStarted,
    UserSpeechEnded,
    UserSpeechStarted,
)
from voice.events import (
    AssistantPlaybackCompleted,
    FollowUpCountdown,
    FollowUpTimedOut,
    VoiceTurnFailed,
    VoiceTurnTimedOut,
    WakeWordDetected,
)
from voice.events.bus import EventBus


class AgentListener:
    """Callback interface for :class:`VoiceAgent` events.

    Subclass this class and pass an instance to ``VoiceAgent(listener=...)``.
    Every callback is an async no-op by default, so subclasses only need to
    override the events they are interested in.
    """

    async def on_agent_starting(self) -> None:
        """The voice session is starting."""

    async def on_agent_stopped(self) -> None:
        """The voice session has ended."""

    async def on_wake_word_detected(
        self, name: str, score: float, sequence: int
    ) -> None:
        """The configured wake word was detected."""

    async def on_user_inactivity_countdown(self, remaining_seconds: int) -> None:
        """A follow-up window is about to expire."""

    async def on_user_inactivity_timeout(self, timeout_seconds: float) -> None:
        """The follow-up window expired without speech."""

    async def on_agent_interrupted(self) -> None:
        """The assistant was interrupted by a repeated wake word."""

    async def on_agent_error(self, turn_id: int, message: str) -> None:
        """A voice turn failed."""

    async def on_voice_turn_timed_out(self, turn_id: int) -> None:
        """No speech was detected before the voice-turn timeout."""

    async def on_user_started_speaking(self) -> None:
        """Voice activity detection found the start of user speech."""

    async def on_user_stopped_speaking(self) -> None:
        """The recorder accepted the end of the user's utterance."""

    async def on_assistant_started_responding(self) -> None:
        """The first assistant audio chunk is about to be played."""

    async def on_assistant_stopped_responding(self) -> None:
        """The assistant audio response completed."""


class AgentListenerBridge:
    def __init__(self, *, event_bus: EventBus, listener: AgentListener) -> None:
        self._event_bus = event_bus
        self._listener = listener

    def setup(self) -> None:
        listener = self._listener
        bus = self._event_bus

        bus.on(SessionStarted, lambda _: listener.on_agent_starting())
        bus.on(SessionEnded, lambda _: listener.on_agent_stopped())
        bus.on(
            WakeWordDetected,
            lambda event: listener.on_wake_word_detected(
                event.name, event.score, event.sequence
            ),
        )
        bus.on(
            FollowUpCountdown,
            lambda event: listener.on_user_inactivity_countdown(
                event.remaining_seconds
            ),
        )
        bus.on(
            FollowUpTimedOut,
            lambda event: listener.on_user_inactivity_timeout(event.timeout_seconds),
        )
        bus.on(AssistantInterrupted, lambda _: listener.on_agent_interrupted())
        bus.on(
            VoiceTurnFailed,
            lambda event: listener.on_agent_error(event.turn_id, event.message),
        )
        bus.on(
            VoiceTurnTimedOut,
            lambda event: listener.on_voice_turn_timed_out(event.turn_id),
        )
        bus.on(UserSpeechStarted, lambda _: listener.on_user_started_speaking())
        bus.on(UserSpeechEnded, lambda _: listener.on_user_stopped_speaking())
        bus.on(
            AssistantSpeechStarted,
            lambda _: listener.on_assistant_started_responding(),
        )
        bus.on(
            AssistantPlaybackCompleted,
            lambda _: listener.on_assistant_stopped_responding(),
        )
