import asyncio
import logging
from collections import defaultdict
from uuid import UUID

from gateway.features.conversation.application import (
    ConversationEvent,
    ConversationEventType,
    EventPublisher,
    SessionService,
)
from gateway.features.conversation.presentation.rpc.models import (
    SessionParams,
    SubscriptionResult,
    UnsubscriptionResult,
)

logger = logging.getLogger(__name__)

_EVENT_PREVIEW_LENGTH = 200


class EventReceiver:
    def __init__(self) -> None:
        self._queue: asyncio.Queue[ConversationEvent] = asyncio.Queue()

    async def receive(self) -> ConversationEvent:
        return await self._queue.get()

    async def put(self, event: ConversationEvent) -> None:
        await self._queue.put(event)


class InMemoryEventStream(EventPublisher):
    def __init__(self) -> None:
        self._clients: dict[str, EventReceiver] = {}
        self._subscriptions: dict[UUID, set[str]] = defaultdict(set)

    def connect(self, client_id: str) -> EventReceiver:
        receiver = EventReceiver()
        self._clients[client_id] = receiver
        return receiver

    def disconnect(self, client_id: str) -> None:
        self._clients.pop(client_id, None)
        for clients in self._subscriptions.values():
            clients.discard(client_id)

    def subscribe(self, client_id: str, session_id: UUID) -> None:
        self._subscriptions[session_id].add(client_id)
        logger.info(
            "Gateway client %s subscribed to session %s",
            _short_id(client_id),
            session_id,
        )

    def unsubscribe(self, client_id: str, session_id: UUID) -> None:
        self._subscriptions[session_id].discard(client_id)
        logger.info(
            "Gateway client %s unsubscribed from session %s",
            _short_id(client_id),
            session_id,
        )

    async def publish(self, event: ConversationEvent) -> None:
        client_ids = tuple(self._subscriptions.get(event.session_id, ()))
        delivered = 0
        for client_id in client_ids:
            receiver = self._clients.get(client_id)
            if receiver is not None:
                await receiver.put(event)
                delivered += 1
        _log_event(event, delivered)


class EventStreamRpcMethods:
    def __init__(
        self,
        sessions: SessionService,
        stream: InMemoryEventStream,
        client_id: str,
    ) -> None:
        self._sessions = sessions
        self._stream = stream
        self._client_id = client_id

    async def subscribe_session(self, params: SessionParams) -> SubscriptionResult:
        await self._sessions.get(params.session_id)
        self._stream.subscribe(self._client_id, params.session_id)
        return SubscriptionResult(subscribed=params.session_id)

    async def unsubscribe_session(
        self,
        params: SessionParams,
    ) -> UnsubscriptionResult:
        self._stream.unsubscribe(self._client_id, params.session_id)
        return UnsubscriptionResult(unsubscribed=params.session_id)


def _log_event(event: ConversationEvent, recipients: int) -> None:
    message = "Emitted event %s for session %s (sequence=%s, recipients=%s%s)"
    detail = _event_detail(event)
    arguments = (
        event.type,
        event.session_id,
        event.sequence,
        recipients,
        detail,
    )
    if event.type is ConversationEventType.CHAT_DELTA:
        logger.debug(message, *arguments)
    else:
        logger.info(message, *arguments)


def _event_detail(event: ConversationEvent) -> str:
    match event.type:
        case ConversationEventType.CHAT_COMPLETED:
            return f", text={_preview(event.data.get('text'))!r}"
        case ConversationEventType.TURN_STEERED:
            return f", text={_preview(event.data.get('text'))!r}"
        case ConversationEventType.TOOL_CALL_STARTED:
            return f", tool={event.data.get('name')!r}, call_id={event.call_id}"
        case ConversationEventType.TOOL_CALL_COMPLETED:
            return (
                f", tool={event.data.get('name')!r}, call_id={event.call_id}, "
                f"error={bool(event.data.get('is_error'))}"
            )
        case ConversationEventType.TURN_FAILED:
            return f", code={event.data.get('code')!r}"
        case _:
            return ""


def _preview(value: object) -> str:
    normalized = " ".join(str(value or "").split())
    if len(normalized) <= _EVENT_PREVIEW_LENGTH:
        return normalized
    return f"{normalized[: _EVENT_PREVIEW_LENGTH - 1]}…"


def _short_id(client_id: str) -> str:
    return client_id[:8]
