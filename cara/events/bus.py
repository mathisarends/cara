import asyncio
import logging
import time
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class BaseEvent:
    """Common root for events dispatched through the bus."""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: float = field(default_factory=time.time)


type EventHandler[T: BaseEvent] = Callable[[T], Awaitable[None]]
type WildcardEventHandler = Callable[[BaseEvent], Awaitable[None]]


class EventBus:
    """Async event bus for independent event handlers."""

    def __init__(self) -> None:
        self._handlers: dict[type[BaseEvent], list[EventHandler]] = {}
        self._wildcard_handlers: list[WildcardEventHandler] = []

    def subscribe[T: BaseEvent](self, event_type: type[T], handler: EventHandler[T]) -> None:
        self._handlers.setdefault(event_type, []).append(handler)
        logger.debug("Subscribed to %s", event_type.__name__)

    def subscribe_all(self, handler: WildcardEventHandler) -> None:
        self._wildcard_handlers.append(handler)
        logger.debug("Subscribed to all events")

    def unsubscribe[T: BaseEvent](self, event_type: type[T], handler: EventHandler[T]) -> None:
        handlers = self._handlers.get(event_type)
        if handlers and handler in handlers:
            handlers.remove(handler)
            if not handlers:
                del self._handlers[event_type]

    def unsubscribe_all(self, handler: WildcardEventHandler) -> None:
        if handler in self._wildcard_handlers:
            self._wildcard_handlers.remove(handler)

    def has_subscribers[T: BaseEvent](self, event_type: type[T]) -> bool:
        return bool(self._handlers.get(event_type)) or bool(self._wildcard_handlers)

    async def dispatch[T: BaseEvent](self, event: T) -> T:
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

    async def wait_for_event[T: BaseEvent](
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
