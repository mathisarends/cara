from abc import ABC, abstractmethod
from uuid import UUID

from gateway.features.automation.domain.automation import Automation


class AutomationRepository(ABC):
    @abstractmethod
    async def find_by_id(self, id: UUID) -> Automation | None: ...

    @abstractmethod
    async def find_by_owner(self, owner_id: str) -> tuple[Automation, ...]: ...

    @abstractmethod
    async def find_all(self) -> tuple[Automation, ...]: ...

    @abstractmethod
    async def save(self, domain: Automation) -> Automation: ...

    @abstractmethod
    async def remove(self, domain: Automation) -> None: ...
