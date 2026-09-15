from abc import ABC, abstractmethod
from datetime import datetime

from gateway.features.automation.domain import AutomationTarget, PromptAction


class AutomationTargetResolver(ABC):
    @abstractmethod
    async def require(self, target: AutomationTarget) -> None: ...


class AutomationActionExecutor(ABC):
    @abstractmethod
    async def execute(
        self,
        automation_id: str,
        target: AutomationTarget,
        action: PromptAction,
        scheduled_for: datetime,
    ) -> None: ...
