import pytest

from gateway.features.automation.application import (
    AutomationService,
    AutomationTargetResolver,
)
from gateway.features.automation.domain import AutomationTarget
from gateway.features.automation.infrastructure.codec import AutomationRecord
from gateway.features.automation.infrastructure.scheduler_repository import (
    SchedulerAutomationRepository,
)
from scheduler import MemoryJobStore, ScheduledRun, Scheduler


class AcceptAllTargets(AutomationTargetResolver):
    async def require(self, target: AutomationTarget) -> None:
        pass


async def _runner(run: ScheduledRun[AutomationRecord]) -> None:
    pass


@pytest.fixture
def automation_scheduler() -> Scheduler[AutomationRecord]:
    return Scheduler(_runner, MemoryJobStore[AutomationRecord]())


@pytest.fixture
def automation_service(
    automation_scheduler: Scheduler[AutomationRecord],
) -> AutomationService:
    repository = SchedulerAutomationRepository(automation_scheduler)
    return AutomationService(repository, AcceptAllTargets())
