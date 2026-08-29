import asyncio
from collections import defaultdict
from uuid import UUID

import pyrpckit as rpc

from gateway.features.conversation.application import (
    ConversationEvent,
    EventPublisher,
    SessionService,
)
from gateway.features.conversation.presentation.rpc.schemas import (
    ConversationRpcMethod,
    SessionParams,
    SubscriptionResult,
    UnsubscriptionResult,
)
from gateway.presentation.rpc import ResourceNotFoundError


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

    def unsubscribe(self, client_id: str, session_id: UUID) -> None:
        self._subscriptions[session_id].discard(client_id)

    async def publish(self, event: ConversationEvent) -> None:
        for client_id in tuple(self._subscriptions.get(event.session_id, ())):
            receiver = self._clients.get(client_id)
            if receiver is not None:
                await receiver.put(event)


class EventStreamRpcMethods(rpc.RpcHandler):
    def __init__(
        self,
        sessions: SessionService,
        stream: InMemoryEventStream,
        client_id: str,
    ) -> None:
        self._sessions = sessions
        self._stream = stream
        self._client_id = client_id

    @rpc.method(
        ConversationRpcMethod.SUBSCRIPTION_SUBSCRIBE,
        errors=(ResourceNotFoundError, rpc.RpcInternalError),
    )
    async def subscribe_session(self, params: SessionParams) -> SubscriptionResult:
        await self._sessions.get(params.session_id)
        self._stream.subscribe(self._client_id, params.session_id)
        return SubscriptionResult(subscribed=params.session_id)

    @rpc.method(
        ConversationRpcMethod.SUBSCRIPTION_UNSUBSCRIBE,
        errors=(rpc.RpcInternalError,),
    )
    async def unsubscribe_session(
        self,
        params: SessionParams,
    ) -> UnsubscriptionResult:
        self._stream.unsubscribe(self._client_id, params.session_id)
        return UnsubscriptionResult(unsubscribed=params.session_id)


EVENT_STREAM_PROTOCOL = rpc.feature(
    "event_stream",
    handlers=(EventStreamRpcMethods,),
)
