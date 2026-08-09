from collections.abc import Awaitable, Callable
from typing import TypeVar, cast

from gateway.features.conversation.domain import AgentEvent

TEvent = TypeVar("TEvent", bound=AgentEvent)
type EventHandler[TEvent: AgentEvent] = Callable[[TEvent], Awaitable[None]]


class AgentEventBus:
    def __init__(self) -> None:
        self._handlers: dict[type[AgentEvent], list[EventHandler[AgentEvent]]] = {}

    def on(
        self,
        event_type: type[TEvent],
        handler: EventHandler[TEvent],
    ) -> None:
        handlers = self._handlers.setdefault(event_type, [])
        handlers.append(cast(EventHandler[AgentEvent], handler))

    async def dispatch(self, event: AgentEvent) -> None:
        for handler in self._handlers.get(type(event), ()):
            await handler(event)
