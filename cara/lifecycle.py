from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cara.assistant import VoiceTurn

logger = logging.getLogger(__name__)


class AssistantState(StrEnum):
    IDLE = "idle"
    LISTENING = "listening"
    TRANSCRIBING = "transcribing"
    THINKING = "thinking"
    SPEAKING = "speaking"


@dataclass(frozen=True)
class StateChanged:
    """Emitted on every phase transition, including the return to ``IDLE``."""

    state: AssistantState


@dataclass(frozen=True)
class TurnStarted:
    """Emitted when a turn begins, before recording starts.

    The assistant does not care what triggered the turn (wake word, button, CLI,
    a test); this just marks the start of the pipeline.
    """


@dataclass(frozen=True)
class Transcribed:
    """Emitted once a non-empty transcript is available."""

    transcript: str


@dataclass(frozen=True)
class AnswerGenerated:
    """Emitted once the LLM produced an answer, before text-to-speech runs."""

    answer: str


@dataclass(frozen=True)
class TurnCompleted:
    """Emitted when a full turn finished successfully."""

    turn: VoiceTurn


type AssistantEvent = StateChanged | TurnStarted | Transcribed | AnswerGenerated | TurnCompleted
"""Closed set of lifecycle events. ``match`` over it to react to specific phases."""


class AssistantLifecycleListener:
    """Hook into the assistant lifecycle to trigger side effects.

    Subclass and override :meth:`on_event`, matching on the event types you care
    about. ``StateChanged`` fires on every transition (handy to drive a single
    state machine, e.g. an LED or UI), while the payload-carrying events let you
    react to a specific phase. All events are awaited; an exception raised by a
    listener is logged and swallowed so it can never abort the voice turn.

    Example::

        class LedListener(AssistantLifecycleListener):
            async def on_event(self, event: AssistantEvent) -> None:
                match event:
                    case StateChanged(state):
                        await self.led.show(state)
                    case Transcribed(transcript):
                        log.info("heard %s", transcript)
    """

    async def on_event(self, event: AssistantEvent) -> None:
        """React to a lifecycle event. Default implementation does nothing."""


class LoggingLifecycleListener(AssistantLifecycleListener):
    """Ready-to-use listener that logs every state change. Handy as an example."""

    def __init__(self, logger: logging.Logger | None = None) -> None:
        self._logger = logger or logging.getLogger(__name__)

    async def on_event(self, event: AssistantEvent) -> None:
        match event:
            case StateChanged(state):
                self._logger.info("Assistant state -> %s", state)
            case _:
                pass
