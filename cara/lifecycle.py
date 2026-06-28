from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

from cara.events import BaseEvent, EventBus

if TYPE_CHECKING:
    from cara.assistant import VoiceTurn

logger = logging.getLogger(__name__)


class AssistantState(StrEnum):
    IDLE = "idle"
    LISTENING = "listening"
    WAITING_FOLLOW_UP = "waiting_follow_up"
    TRANSCRIBING = "transcribing"
    THINKING = "thinking"
    SPEAKING = "speaking"


@dataclass(frozen=True)
class StateChanged(BaseEvent):
    """Emitted on every phase transition, including the return to ``IDLE``."""

    state: AssistantState


@dataclass(frozen=True)
class TurnStarted(BaseEvent):
    """Emitted when a turn begins, before recording starts.

    The assistant does not care what triggered the turn (wake word, button, CLI,
    a test); this just marks the start of the pipeline.
    """


@dataclass(frozen=True)
class SessionStarted(BaseEvent):
    """Emitted when a multi-turn voice session begins."""


@dataclass(frozen=True)
class SessionEnded(BaseEvent):
    """Emitted when a multi-turn voice session ends."""


@dataclass(frozen=True)
class Transcribed(BaseEvent):
    """Emitted once a non-empty transcript is available."""

    transcript: str


@dataclass(frozen=True)
class AnswerGenerated(BaseEvent):
    """Emitted once the LLM produced an answer, before text-to-speech runs."""

    answer: str


@dataclass(frozen=True)
class TurnCompleted(BaseEvent):
    """Emitted when a full turn finished successfully."""

    turn: VoiceTurn


type AssistantEvent = (
    StateChanged | SessionStarted | SessionEnded | TurnStarted | Transcribed | AnswerGenerated | TurnCompleted
)
"""Closed set of assistant events."""


class LoggingLifecycleListener:
    """Ready-to-use listener that logs every state change."""

    def __init__(self, event_bus: EventBus, logger: logging.Logger | None = None) -> None:
        self._logger = logger or logging.getLogger(__name__)
        event_bus.subscribe(StateChanged, self.on_state_changed)

    async def on_state_changed(self, event: StateChanged) -> None:
        self._logger.info("Assistant state -> %s", event.state)
