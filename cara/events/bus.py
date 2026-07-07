import asyncio
import logging
from collections.abc import Awaitable, Callable

from .views import Event

logger = logging.getLogger(__name__)


type EventHandler[T: Event] = Callable[[T], Awaitable[None]]
type WildcardEventHandler = Callable[[Event], Awaitable[None]]


class EventBus:
    def __init__(self) -> None:
        self._handlers: dict[type[Event], list[EventHandler]] = {}
        self._wildcard_handlers: list[WildcardEventHandler] = []

    def subscribe[T: Event](self, event_type: type[T], handler: EventHandler[T]) -> None:
        self._handlers.setdefault(event_type, []).append(handler)
        logger.debug("Subscribed to %s", event_type.__name__)

    def subscribe_all(self, handler: WildcardEventHandler) -> None:
        self._wildcard_handlers.append(handler)
        logger.debug("Subscribed to all events")

    def unsubscribe[T: Event](self, event_type: type[T], handler: EventHandler[T]) -> None:
        handlers = self._handlers.get(event_type)
        if handlers and handler in handlers:
            handlers.remove(handler)
            if not handlers:
                del self._handlers[event_type]

    def unsubscribe_all(self, handler: WildcardEventHandler) -> None:
        if handler in self._wildcard_handlers:
            self._wildcard_handlers.remove(handler)

    def has_subscribers[T: Event](self, event_type: type[T]) -> bool:
        return bool(self._handlers.get(event_type)) or bool(self._wildcard_handlers)

    async def dispatch[T: Event](self, event: T) -> T:
        event_type = type(event)
        handlers = [*self._handlers.get(event_type, []), *self._wildcard_handlers]
        if not handlers:
            logger.debug("No handlers registered for %s", event_type.__name__)
            return event

        results = await asyncio.gather(
            *(handler(event) for handler in handlers),
            return_exceptions=True,
        )
        for result in results:
            if isinstance(result, Exception):
                logger.error(
                    "Handler failed for %s",
                    event_type.__name__,
                    exc_info=(type(result), result, result.__traceback__),
                )
        return event

    async def wait_for_event[T: Event](
        self,
        event_type: type[T],
        timeout: float | None = None,
        predicate: Callable[[T], bool] | None = None,
    ) -> T:
        loop = asyncio.get_running_loop()
        future: asyncio.Future[T] = loop.create_future()

        async def handler(event: T) -> None:
            if (predicate is None or predicate(event)) and not future.done():
                future.set_result(event)

        self.subscribe(event_type, handler)
        try:
            if timeout is None:
                return await future
            return await asyncio.wait_for(future, timeout=timeout)
        finally:
            self.unsubscribe(event_type, handler)
