import asyncio
import logging
from collections.abc import Awaitable, Callable

from pydantic import BaseModel

logger = logging.getLogger(__name__)

type Handler[E: BaseModel] = Callable[[E], Awaitable[object]]


class EventBus:
    def __init__(self) -> None:
        self._handlers: dict[type[BaseModel], list[Handler]] = {}

    def on[E: BaseModel](self, event_type: type[E], handler: Handler[E]) -> Handler[E]:
        self._handlers.setdefault(event_type, []).append(handler)
        return handler

    def off[E: BaseModel](self, event_type: type[E], handler: Handler[E]) -> None:
        handlers = self._handlers.get(event_type)
        if handlers and handler in handlers:
            handlers.remove(handler)

    async def dispatch(self, event: BaseModel) -> None:
        handlers = tuple(self._handlers.get(type(event), ()))
        await asyncio.gather(*(_run_handler(handler, event) for handler in handlers))


async def _run_handler(handler: Handler, event: BaseModel) -> None:
    try:
        await handler(event)
    except Exception:
        logger.exception("Event handler failed for %s", type(event).__name__)
