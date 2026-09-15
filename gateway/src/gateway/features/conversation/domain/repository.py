from abc import ABC, abstractmethod
from uuid import UUID

from gateway.features.conversation.domain.session import Session
from gateway.features.conversation.domain.values import ChannelRef, SortOrder


class SessionRepository(ABC):
    @abstractmethod
    async def find_by_id(self, id: UUID) -> Session | None: ...

    @abstractmethod
    async def find_latest_by_channel(self, channel: ChannelRef) -> Session | None: ...

    @abstractmethod
    async def find_many(
        self, *, limit: int, order: SortOrder
    ) -> tuple[Session, ...]: ...

    @abstractmethod
    async def save(self, domain: Session) -> Session: ...
