import asyncio
from collections import defaultdict
from uuid import UUID

from gateway.features.conversation.application import EventBroker, EventReceiver
from gateway.features.conversation.domain import GatewayEvent


class _QueueEventReceiver(EventReceiver):
    def __init__(self) -> None:
        self._queue: asyncio.Queue[GatewayEvent] = asyncio.Queue()

    async def receive(self) -> GatewayEvent:
        return await self._queue.get()

    async def put(self, event: GatewayEvent) -> None:
        await self._queue.put(event)


class InMemoryEventBroker(EventBroker):
    def __init__(self) -> None:
        self._clients: dict[str, _QueueEventReceiver] = {}
        self._subscriptions: dict[UUID, set[str]] = defaultdict(set)

    def connect(self, client_id: str) -> EventReceiver:
        receiver = _QueueEventReceiver()
        self._clients[client_id] = receiver
        return receiver

    def disconnect(self, client_id: str) -> None:
        self._clients.pop(client_id, None)
        for clients in self._subscriptions.values():
            clients.discard(client_id)

    def subscribe(self, client_id: str, session_id: UUID) -> None:
        self._subscriptions[session_id].add(client_id)

    async def publish(self, event: GatewayEvent) -> None:
        if event.session_id is None:
            return
        for client_id in tuple(self._subscriptions.get(event.session_id, ())):
            receiver = self._clients.get(client_id)
            if receiver is not None:
                await receiver.put(event)
