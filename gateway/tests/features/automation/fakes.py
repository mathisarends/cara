from datetime import UTC, datetime
from uuid import UUID

from gateway.features.automation.application import (
    AutomationActionExecutor,
    AutomationScheduler,
    AutomationTargetResolver,
)
from gateway.features.automation.domain import (
    Automation,
    AutomationSchedule,
    AutomationTarget,
    PromptAction,
)
from gateway.shared.transaction import Transaction, TransactionAction


class ImmediateTransaction(Transaction):
    def after_commit(self, action: TransactionAction) -> None:
        action()


class AcceptAllTargets(AutomationTargetResolver):
    async def require(self, target: AutomationTarget) -> None:
        pass


class RecordingScheduler(AutomationScheduler):
    def __init__(self) -> None:
        self.next_run_at = datetime(2027, 1, 1, 9, tzinfo=UTC)
        self.armed: dict[UUID, datetime] = {}

    def first_run_at(self, schedule: AutomationSchedule) -> datetime:
        return self.next_run_at

    def arm(self, automation: Automation) -> None:
        self.armed[automation.id] = automation.next_run_at

    def disarm(self, automation: Automation) -> None:
        self.armed.pop(automation.id, None)


class RecordingExecutor(AutomationActionExecutor):
    def __init__(self, error: Exception | None = None) -> None:
        self.executed: list[UUID] = []
        self._error = error

    async def execute(
        self,
        automation_id: UUID,
        target: AutomationTarget,
        action: PromptAction,
        scheduled_for: datetime,
    ) -> None:
        self.executed.append(automation_id)
        if self._error is not None:
            raise self._error
