import asyncio
import logging
from collections.abc import Awaitable, Callable

from voice.events.models import Event, Request

logger = logging.getLogger(__name__)

type EventHandler[E: Event] = Callable[[E], Awaitable[object]]
type RequestHandler[R: Request] = Callable[[R], Awaitable[object]]


class EventBus:
    """Broadcasts events to any number of listeners and routes requests to one."""

    def __init__(self) -> None:
        self._event_handlers: dict[type[Event], list[EventHandler]] = {}
        self._request_handlers: dict[type[Request], RequestHandler] = {}

    def on[E: Event](
        self, event_type: type[E], handler: EventHandler[E]
    ) -> EventHandler[E]:
        self._event_handlers.setdefault(event_type, []).append(handler)
        return handler

    def off[E: Event](self, event_type: type[E], handler: EventHandler[E]) -> None:
        handlers = self._event_handlers.get(event_type)
        if handlers and handler in handlers:
            handlers.remove(handler)

    def on_request[R: Request](
        self, request_type: type[R], handler: RequestHandler[R]
    ) -> RequestHandler[R]:
        if request_type in self._request_handlers:
            raise RuntimeError(f"{request_type.__name__} already has a handler.")
        self._request_handlers[request_type] = handler
        return handler

    async def dispatch(self, event: Event) -> None:
        """Notify every listener; a failing listener is logged, never raised."""
        handlers = tuple(self._event_handlers.get(type(event), ()))
        await asyncio.gather(*(_notify(handler, event) for handler in handlers))

    async def request(self, request: Request) -> None:
        """Run the registered handler; its failures propagate to the caller."""
        handler = self._request_handlers.get(type(request))
        if handler is None:
            raise LookupError(f"No handler registered for {type(request).__name__}.")
        await handler(request)


async def _notify(handler: EventHandler, event: Event) -> None:
    try:
        await handler(event)
    except Exception:
        logger.exception("Event handler failed for %s", type(event).__name__)
