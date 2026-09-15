from abc import ABC, abstractmethod

from gateway.features.automation.domain.automation import Automation


class AutomationRepository(ABC):
    @abstractmethod
    async def list_for_owner(self, owner_id: str) -> tuple[Automation, ...]: ...

    @abstractmethod
    async def get(self, automation_id: str) -> Automation | None: ...

    @abstractmethod
    async def save(self, automation: Automation) -> Automation: ...

    @abstractmethod
    async def remove(self, automation: Automation) -> None: ...
