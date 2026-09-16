from asyncio import CancelledError, gather
from collections.abc import Awaitable, Callable
from typing import Any, cast

from voice.events.errors import NoSubscriberError
from voice.events.models import Event, Request
from voice.events.subscription import EventHandler, Subscription

type RequestHandler[R: Request] = Callable[[R], Awaitable[object]]


class EventBus:
    """Broadcasts events to any number of listeners and routes requests to one.

    ``emit`` awaits all matching handlers and propagates their failures. Set
    ``require_subscribers`` when delivery without a handler is invalid.
    """

    def __init__(self) -> None:
        self._subscriptions: list[Subscription] = []
        self._request_handlers: dict[type[Request], RequestHandler] = {}

    def on[E: Event](
        self,
        event_type: type[E],
        handler: EventHandler[E],
        *,
        name: str | None = None,
    ) -> Subscription:
        """Register a handler and return its closable subscription."""
        subscription = Subscription(
            self, event_type, cast(EventHandler[Any], handler), name
        )
        self._subscriptions.append(subscription)
        return subscription

    async def emit[E: Event](
        self,
        event: E,
        *,
        require_subscribers: bool = False,
    ) -> None:
        """Deliver to all captured handlers and await their completion."""
        handlers = [
            subscription.handler
            for subscription in tuple(self._subscriptions)
            if not subscription.closed and isinstance(event, subscription.event_type)
        ]
        if not handlers:
            if require_subscribers:
                raise NoSubscriberError(
                    f"No subscriber registered for {type(event).__name__}"
                )
            return

        results = await gather(
            *(handler(event) for handler in handlers), return_exceptions=True
        )
        cancellations = [
            result for result in results if isinstance(result, CancelledError)
        ]
        if cancellations:
            raise cancellations[0]
        fatal_errors = [
            result
            for result in results
            if isinstance(result, BaseException) and not isinstance(result, Exception)
        ]
        if fatal_errors:
            raise fatal_errors[0]
        errors = [result for result in results if isinstance(result, Exception)]
        if len(errors) == 1:
            raise errors[0]
        if errors:
            raise ExceptionGroup(f"Handlers failed for {type(event).__name__}", errors)

    def on_request[R: Request](
        self, request_type: type[R], handler: RequestHandler[R]
    ) -> RequestHandler[R]:
        if request_type in self._request_handlers:
            raise RuntimeError(f"{request_type.__name__} already has a handler.")
        self._request_handlers[request_type] = handler
        return handler

    async def request(self, request: Request) -> None:
        """Run the registered handler; its failures propagate to the caller."""
        handler = self._request_handlers.get(type(request))
        if handler is None:
            raise LookupError(f"No handler registered for {type(request).__name__}.")
        await handler(request)

    def subscriptions(
        self, event_type: type[Event] | None = None
    ) -> tuple[Subscription, ...]:
        """Return active subscriptions for wiring diagnostics."""
        return tuple(
            subscription
            for subscription in self._subscriptions
            if not subscription.closed
            and (event_type is None or subscription.event_type is event_type)
        )

    def has_subscribers(self, event_type: type[Event]) -> bool:
        return bool(self.subscriptions(event_type))

    def _remove(self, subscription: Subscription) -> None:
        if subscription in self._subscriptions:
            self._subscriptions.remove(subscription)
