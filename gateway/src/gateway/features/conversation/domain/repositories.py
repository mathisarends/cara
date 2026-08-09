from abc import ABC, abstractmethod
from uuid import UUID

from gateway.features.conversation.domain.session import Session


class SessionRepository(ABC):
    @abstractmethod
    async def find_by_id(self, id: UUID) -> Session | None: ...

    @abstractmethod
    async def save(self, domain: Session) -> Session: ...

    @abstractmethod
    async def claim_turn(self, id: UUID) -> bool: ...

    @abstractmethod
    async def release_turn(self, id: UUID) -> None: ...
