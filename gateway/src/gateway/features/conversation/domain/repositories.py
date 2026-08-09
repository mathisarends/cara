from abc import ABC, abstractmethod
from uuid import UUID

from gateway.features.conversation.domain.models import Run, Session


class SessionRepository(ABC):
    @abstractmethod
    async def find_by_id(self, id: UUID) -> Session | None: ...

    @abstractmethod
    async def save(self, domain: Session) -> Session: ...


class RunRepository(ABC):
    @abstractmethod
    async def find_by_id(self, id: UUID) -> Run | None: ...

    @abstractmethod
    async def save(self, domain: Run) -> Run: ...
