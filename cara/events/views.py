from enum import StrEnum

from transitbus import Event


class AssistantState(StrEnum):
    IDLE = "idle"
    LISTENING = "listening"
    WAITING_FOLLOW_UP = "waiting_follow_up"
    TRANSCRIBING = "transcribing"
    THINKING = "thinking"
    CALLING_TOOL = "calling_tool"
    SPEAKING = "speaking"


class StateChanged(Event):
    """Emitted on every phase transition, including the return to ``IDLE``."""

    state: AssistantState


class TurnStarted(Event):
    """Emitted when a turn begins, before recording starts.

    The assistant does not care what triggered the turn (wake word, button, CLI,
    a test); this just marks the start of the pipeline.
    """


class SessionStarted(Event):
    """Emitted when a multi-turn voice session begins."""


class SessionEnded(Event):
    """Emitted when a multi-turn voice session ends."""


class Transcribed(Event):
    """Emitted once a non-empty transcript is available."""

    transcript: str


class AnswerGenerated(Event):
    """Emitted once the full answer is known; streamed speech may already be playing."""

    answer: str


class Interrupted(Event):
    """Emitted when a repeated wake word interrupts an in-flight assistant response."""

    phase: AssistantState
