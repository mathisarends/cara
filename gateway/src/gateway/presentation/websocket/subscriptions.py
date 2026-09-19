import asyncio
import logging
from collections import defaultdict
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from uuid import UUID

from gateway.features.conversation.application import (
    ConversationEvent,
    ConversationEventType,
    EventPublisher,
    EventSource,
    EventSubscription,
)
from gateway.features.voice.application import VoiceEvent, VoiceEventPublisher

logger = logging.getLogger(__name__)

_EVENT_PREVIEW_LENGTH = 200


class EventReceiver:
    def __init__(self) -> None:
        self._queue: asyncio.Queue[ConversationEvent] = asyncio.Queue()
        self._voice_queue: asyncio.Queue[VoiceEvent] = asyncio.Queue()

    async def receive(self) -> ConversationEvent:
        return await self._queue.get()

    async def put(self, event: ConversationEvent) -> None:
        await self._queue.put(event)

    async def receive_voice(self) -> VoiceEvent:
        return await self._voice_queue.get()

    async def put_voice(self, event: VoiceEvent) -> None:
        await self._voice_queue.put(event)


@dataclass(frozen=True, slots=True)
class GatewayClient:
    id: str
    receiver: EventReceiver


class _InternalEventSubscription(EventSubscription):
    def __init__(self) -> None:
        self._queue: asyncio.Queue[ConversationEvent] = asyncio.Queue()

    async def receive(self) -> ConversationEvent:
        return await self._queue.get()

    async def put(self, event: ConversationEvent) -> None:
        await self._queue.put(event)


class InMemoryEventStream(EventPublisher, EventSource, VoiceEventPublisher):
    def __init__(self) -> None:
        self._clients: dict[str, EventReceiver] = {}
        self._subscriptions: dict[UUID, set[str]] = defaultdict(set)
        self._channel_subscriptions: dict[str, set[str]] = defaultdict(set)
        self._internal_subscriptions: dict[UUID, set[_InternalEventSubscription]] = (
            defaultdict(set)
        )

    @asynccontextmanager
    async def listen(
        self,
        session_id: UUID,
    ) -> AsyncIterator[EventSubscription]:
        subscription = _InternalEventSubscription()
        self._internal_subscriptions[session_id].add(subscription)
        try:
            yield subscription
        finally:
            subscriptions = self._internal_subscriptions[session_id]
            subscriptions.discard(subscription)
            if not subscriptions:
                self._internal_subscriptions.pop(session_id, None)

    def connect(self, client_id: str) -> EventReceiver:
        receiver = EventReceiver()
        self._clients[client_id] = receiver
        return receiver

    def disconnect(self, client_id: str) -> None:
        self._clients.pop(client_id, None)
        for clients in self._subscriptions.values():
            clients.discard(client_id)
        for clients in self._channel_subscriptions.values():
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

    def subscribe_channel(self, client_id: str, channel: str) -> None:
        self._channel_subscriptions[channel].add(client_id)
        logger.info(
            "Gateway client %s subscribed to channel %s",
            _short_id(client_id),
            channel,
        )

    def unsubscribe_channel(self, client_id: str, channel: str) -> None:
        self._channel_subscriptions[channel].discard(client_id)
        logger.info(
            "Gateway client %s unsubscribed from channel %s",
            _short_id(client_id),
            channel,
        )

    async def publish(self, event: ConversationEvent) -> None:
        client_ids = self._subscriptions.get(event.session_id, set()) | (
            self._channel_subscriptions.get(event.channel.name, set())
        )
        delivered = 0
        for client_id in client_ids:
            receiver = self._clients.get(client_id)
            if receiver is not None:
                await receiver.put(event)
                delivered += 1
        for subscription in tuple(
            self._internal_subscriptions.get(event.session_id, set())
        ):
            await subscription.put(event)
        _log_event(event, delivered)

    async def publish_voice(self, event: VoiceEvent) -> None:
        delivered = 0
        for client_id in self._subscriptions.get(event.session_id, set()):
            receiver = self._clients.get(client_id)
            if receiver is not None:
                await receiver.put_voice(event)
                delivered += 1
        logger.info(
            "Emitted voice event %s for session %s (sequence=%s, recipients=%s)",
            event.type,
            event.session_id,
            event.sequence,
            delivered,
        )


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
