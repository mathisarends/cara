from abc import ABC, abstractmethod
from datetime import datetime
from uuid import UUID

from gateway.features.automation.domain import PromptAction, SessionTarget


class AutomationTargetResolver(ABC):
    @abstractmethod
    async def require_session(self, session_id: UUID) -> None: ...


class AutomationActionExecutor(ABC):
    @abstractmethod
    async def execute(
        self,
        automation_id: str,
        target: SessionTarget,
        action: PromptAction,
        scheduled_for: datetime,
    ) -> None: ...
