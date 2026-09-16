from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any, Self

from voice.events.models import Event

if TYPE_CHECKING:
    from voice.events.bus import EventBus

type EventHandler[E: Event] = Callable[[E], Awaitable[None]]


class Subscription:
    """A handler registration with an explicit lifetime."""

    def __init__(
        self,
        bus: EventBus,
        event_type: type[Event],
        handler: EventHandler[Any],
        name: str | None,
    ) -> None:
        self._bus = bus
        self.event_type = event_type
        self.handler = handler
        self.name = name
        self.closed = False

    def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        self._bus._remove(self)

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *_: object) -> None:
        self.close()
