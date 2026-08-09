from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from uuid import UUID

from gateway.features.conversation.domain import (
    AgentOutput,
    GatewayEvent,
    Session,
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
    async def publish_to(self, client_id: str, event: GatewayEvent) -> None: ...


class AgentRunner(ABC):
    @abstractmethod
    def stream(
        self,
        session: Session,
        text: str,
        metadata: dict[str, object],
    ) -> AsyncIterator[AgentOutput]: ...
