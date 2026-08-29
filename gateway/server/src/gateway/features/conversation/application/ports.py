from abc import ABC, abstractmethod
from uuid import UUID

from gateway.features.conversation.application.events import ConversationEvent


class EventPublisher(ABC):
    @abstractmethod
    async def publish(self, event: ConversationEvent) -> None: ...


class TurnLease(ABC):
    @abstractmethod
    async def acquire(self, session_id: UUID) -> bool: ...

    @abstractmethod
    async def release(self, session_id: UUID) -> None: ...
