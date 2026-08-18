import asyncio
import logging
from collections.abc import Awaitable, Callable, Sequence

from voice.events.models import Event, Request

logger = logging.getLogger(__name__)

type EventHandler[E: Event] = Callable[[E], Awaitable[object]]
type RequestHandler[R: Request] = Callable[[R], Awaitable[object]]


class Dispatch:
    """The outcome of one fan-out, carrying every listener that failed."""

    def __init__(self, event: Event, failures: Sequence[Exception]) -> None:
        self._event = event
        self._failures = tuple(failures)

    def raise_if_failed(self) -> None:
        if not self._failures:
            return
        raise ExceptionGroup(
            f"Listeners failed for {type(self._event).__name__}",
            list(self._failures),
        )


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

    async def dispatch(self, event: Event) -> Dispatch:
        """Notify every listener; failures are logged and returned, never raised.

        Callers that cannot continue without their listeners succeeding call
        `raise_if_failed` on the result.
        """
        handlers = tuple(self._event_handlers.get(type(event), ()))
        failures = await asyncio.gather(
            *(_notify(handler, event) for handler in handlers)
        )
        return Dispatch(event, [failure for failure in failures if failure is not None])

    async def request(self, request: Request) -> None:
        """Run the registered handler; its failures propagate to the caller."""
        handler = self._request_handlers.get(type(request))
        if handler is None:
            raise LookupError(f"No handler registered for {type(request).__name__}.")
        await handler(request)


async def _notify(handler: EventHandler, event: Event) -> Exception | None:
    try:
        await handler(event)
    except Exception as error:
        logger.exception("Event handler failed for %s", type(event).__name__)
        return error
    return None
