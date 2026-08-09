from abc import ABC, abstractmethod
from collections.abc import AsyncIterator

from gateway.application.models import AgentOutput, GatewayEvent, Run, Session


class SessionRepository(ABC):
    @abstractmethod
    async def add(self, session: Session) -> None: ...

    @abstractmethod
    async def get(self, session_id: str) -> Session | None: ...


class RunRepository(ABC):
    @abstractmethod
    async def add(self, run: Run) -> None: ...

    @abstractmethod
    async def get(self, run_id: str) -> Run | None: ...


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
    def subscribe(self, client_id: str, session_id: str) -> None: ...

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
