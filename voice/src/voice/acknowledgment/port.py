from abc import ABC, abstractmethod
from dataclasses import dataclass

from voice.events.bus import EventBus


@dataclass(frozen=True, slots=True)
class AcknowledgmentContext:
    """The session an acknowledgment is delivered into."""

    event_bus: EventBus


class AcknowledgmentStrategy(ABC):
    """Delivers immediate feedback once the user has stopped speaking."""

    def __init__(self) -> None:
        self._context: AcknowledgmentContext | None = None

    def set_context(self, context: AcknowledgmentContext) -> None:
        """Bind to the session.

        The voice agent calls this while wiring itself up, so a strategy is
        constructed like any other collaborator and learns about the session
        afterwards.
        """
        self._context = context

    @abstractmethod
    async def acknowledge(self, phrase: str) -> None: ...

    def _prepared_context(self) -> AcknowledgmentContext:
        if self._context is None:
            raise RuntimeError("AcknowledgmentStrategy must be bound to a context.")
        return self._context
