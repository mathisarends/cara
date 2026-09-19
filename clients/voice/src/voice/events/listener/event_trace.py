import logging
from collections import Counter
from uuid import UUID

from voice.events.bus import EventBus
from voice.events.models import (
    AssistantAudioChunk,
    Event,
    UserAudioChunk,
)

logger = logging.getLogger(__name__)

_MAX_VALUE_LENGTH = 60
_REPEATING = (
    AssistantAudioChunk,
    UserAudioChunk,
)


class EventTrace:
    """Logs every event on the bus in the order it was emitted.

    A voice turn is driven by three independent gateway streams and a dozen
    listeners, so the interleaving of their events is the only evidence of
    where a turn stopped making progress. Streamed chunks are counted instead
    of logged so the landmarks around them stay readable.
    """

    def __init__(self, event_bus: EventBus) -> None:
        self._repetitions: Counter[str] = Counter()
        event_bus.on(Event, self._on_event, name="event-trace")

    async def _on_event(self, event: Event) -> None:
        if not logger.isEnabledFor(logging.DEBUG):
            return
        if isinstance(event, _REPEATING):
            self._repetitions[type(event).__name__] += 1
            return
        self._flush()
        logger.debug("%s", _describe(event))

    def _flush(self) -> None:
        for name, count in self._repetitions.items():
            logger.debug("%s x%d", name, count)
        self._repetitions.clear()


def _describe(event: Event) -> str:
    fields = ", ".join(
        f"{name}={_render(value)}" for name, value in event.model_dump().items()
    )
    return f"{type(event).__name__}({fields})"


def _render(value: object) -> str:
    if isinstance(value, UUID):
        return str(value)[:8]
    rendered = repr(value)
    if len(rendered) > _MAX_VALUE_LENGTH:
        return f"{rendered[:_MAX_VALUE_LENGTH]}..."
    return rendered
