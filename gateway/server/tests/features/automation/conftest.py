from uuid import UUID

import pytest

from gateway.features.automation.application import (
    AutomationTargetResolver,
    SessionAutomationService,
)
from gateway.features.automation.infrastructure.codec import AutomationRecord
from gateway.features.automation.infrastructure.scheduler_repository import (
    SchedulerAutomationRepository,
)
from scheduler import MemoryJobStore, ScheduledRun, Scheduler


class AcceptAllSessions(AutomationTargetResolver):
    async def require_session(self, session_id: UUID) -> None:
        pass


async def _runner(run: ScheduledRun[AutomationRecord]) -> None:
    pass


@pytest.fixture
def automation_scheduler() -> Scheduler[AutomationRecord]:
    return Scheduler(_runner, MemoryJobStore[AutomationRecord]())


@pytest.fixture
def automation_service(
    automation_scheduler: Scheduler[AutomationRecord],
) -> SessionAutomationService:
    repository = SchedulerAutomationRepository(automation_scheduler)
    return SessionAutomationService(repository, AcceptAllSessions())
