from abc import ABC, abstractmethod
from uuid import UUID

from gateway.features.conversation.domain import (
    GatewayEvent,
)


class EventPublisher(ABC):
    @abstractmethod
    async def publish(self, event: GatewayEvent) -> None: ...


class EventReceiver(ABC):
    @abstractmethod
    async def receive(self) -> GatewayEvent: ...


class EventBroker(EventPublisher):
    @abstractmethod
    def connect(self, client_id: str) -> EventReceiver: ...

    @abstractmethod
    def disconnect(self, client_id: str) -> None: ...

    @abstractmethod
    def subscribe(self, client_id: str, session_id: UUID) -> None: ...

    @abstractmethod
    def unsubscribe(self, client_id: str, session_id: UUID) -> None: ...
