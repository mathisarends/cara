"""Console listener: logs each phase of a voice turn.

A minimal example of a lifecycle listener. Subscribe only to the events you care
about - this is where you'd drive an LED ring, update a UI, play earcons, etc.
"""

import logging

from cara.events import (
    AnswerGenerated,
    EventBus,
    SessionEnded,
    SessionStarted,
    StateChanged,
    Transcribed,
)

logger = logging.getLogger(__name__)


class ConsoleListener:
    """Logs the assistant lifecycle to the console."""

    def __init__(self, event_bus: EventBus) -> None:
        self._event_bus = event_bus
        self._event_bus.subscribe(StateChanged, self._on_state_changed)
        self._event_bus.subscribe(SessionStarted, self._on_session_started)
        self._event_bus.subscribe(SessionEnded, self._on_session_ended)
        self._event_bus.subscribe(Transcribed, self._on_transcribed)
        self._event_bus.subscribe(AnswerGenerated, self._on_answer_generated)

    async def _on_state_changed(self, event: StateChanged) -> None:
        logger.info("[state] %s", event.state)

    async def _on_session_started(self, event: SessionStarted) -> None:
        logger.info("[session] started")

    async def _on_session_ended(self, event: SessionEnded) -> None:
        logger.info("[session] ended")

    async def _on_transcribed(self, event: Transcribed) -> None:
        logger.info("[heard] %s", event.transcript)

    async def _on_answer_generated(self, event: AnswerGenerated) -> None:
        logger.info("[answer] %s", event.answer)
