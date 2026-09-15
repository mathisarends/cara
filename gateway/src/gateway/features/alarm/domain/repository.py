from abc import ABC, abstractmethod
from uuid import UUID

from gateway.features.alarm.domain.alarm import Alarm


class AlarmRepository(ABC):
    @abstractmethod
    async def find_by_id(self, id: UUID) -> Alarm | None: ...

    @abstractmethod
    async def find_by_owner(self, owner_id: str) -> tuple[Alarm, ...]: ...

    @abstractmethod
    async def find_all(self) -> tuple[Alarm, ...]: ...

    @abstractmethod
    async def save(self, domain: Alarm) -> Alarm: ...

    @abstractmethod
    async def remove(self, domain: Alarm) -> None: ...
