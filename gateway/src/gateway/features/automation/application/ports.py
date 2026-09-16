from abc import ABC, abstractmethod
from datetime import datetime
from uuid import UUID

from gateway.features.automation.domain import (
    Automation,
    AutomationSchedule,
    AutomationTarget,
    PromptAction,
)
from gateway.shared import VoiceDelivery


class AutomationTargetResolver(ABC):
    @abstractmethod
    async def require(self, target: AutomationTarget) -> None: ...


class AutomationActionExecutor(ABC):
    @abstractmethod
    async def execute(
        self,
        automation_id: UUID,
        target: AutomationTarget,
        action: PromptAction,
        delivery: VoiceDelivery | None,
        scheduled_for: datetime,
    ) -> None: ...


class AutomationScheduler(ABC):
    """Runtime timer for persisted automations; it never owns their state."""

    @abstractmethod
    def first_run_at(self, schedule: AutomationSchedule) -> datetime: ...

    @abstractmethod
    def arm(self, automation: Automation) -> None:
        """Start or replace the timer, resuming at ``automation.next_run_at``."""

    @abstractmethod
    def disarm(self, automation: Automation) -> None: ...
