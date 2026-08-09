from abc import ABC, abstractmethod

from gateway.features.conversation.domain.models import Run, Session


class SessionRepository(ABC):
    @abstractmethod
    async def find_by_id(self, id: str) -> Session | None: ...

    @abstractmethod
    async def save(self, domain: Session) -> Session: ...


class RunRepository(ABC):
    @abstractmethod
    async def find_by_id(self, id: str) -> Run | None: ...

    @abstractmethod
    async def save(self, domain: Run) -> Run: ...
