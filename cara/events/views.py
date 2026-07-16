import time
import uuid
from dataclasses import dataclass, field
from enum import StrEnum


@dataclass(frozen=True, kw_only=True)
class Event:
    """Common root for events dispatched through the bus."""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: float = field(default_factory=time.time)


class AssistantState(StrEnum):
    IDLE = "idle"
    LISTENING = "listening"
    WAITING_FOLLOW_UP = "waiting_follow_up"
    TRANSCRIBING = "transcribing"
    THINKING = "thinking"
    CALLING_TOOL = "calling_tool"
    SPEAKING = "speaking"


@dataclass(frozen=True, kw_only=True)
class StateChanged(Event):
    """Emitted on every phase transition, including the return to ``IDLE``."""

    state: AssistantState


@dataclass(frozen=True, kw_only=True)
class TurnStarted(Event):
    """Emitted when a turn begins, before recording starts.

    The assistant does not care what triggered the turn (wake word, button, CLI,
    a test); this just marks the start of the pipeline.
    """


@dataclass(frozen=True, kw_only=True)
class SessionStarted(Event):
    """Emitted when a multi-turn voice session begins."""


@dataclass(frozen=True, kw_only=True)
class SessionEnded(Event):
    """Emitted when a multi-turn voice session ends."""


@dataclass(frozen=True, kw_only=True)
class Transcribed(Event):
    """Emitted once a non-empty transcript is available."""

    transcript: str


@dataclass(frozen=True, kw_only=True)
class AnswerGenerated(Event):
    """Emitted once the full answer is known; streamed speech may already be playing."""

    answer: str


@dataclass(frozen=True, kw_only=True)
class Interrupted(Event):
    """Emitted when user speech interrupts an in-flight assistant response."""

    phase: AssistantState
