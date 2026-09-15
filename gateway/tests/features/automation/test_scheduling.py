import asyncio
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from features.automation.fakes import AcceptAllTargets, RecordingExecutor
from gateway.features.automation.application import (
    AutomationExecution,
    AutomationService,
)
from gateway.features.automation.domain import (
    AtSchedule,
    Automation,
    AutomationOrigin,
    IntervalSchedule,
    PromptAction,
    SessionTarget,
)
from gateway.features.automation.infrastructure.repository import (
    SQLAutomationRepository,
)
from gateway.features.automation.infrastructure.scheduling import (
    AutomationJobRunner,
    InProcessAutomationScheduler,
)
from scheduler import Scheduler


async def test_a_due_one_shot_runs_once_and_is_removed(
    automation_repository: SQLAutomationRepository,
) -> None:
    executor = RecordingExecutor()
    scheduler = _scheduler(automation_repository, executor)
    service = AutomationService(
        automation_repository,
        AcceptAllTargets(),
        InProcessAutomationScheduler(scheduler),
    )

    await scheduler.start()
    try:
        automation = await service.create(
            "owner",
            target=SessionTarget(uuid4()),
            schedule=AtSchedule(run_at=datetime.now(UTC) + timedelta(milliseconds=20)),
            action=PromptAction("Stand up"),
            origin=AutomationOrigin(uuid4()),
        )
        async with asyncio.timeout(1):
            while await automation_repository.find_by_id(automation.id) is not None:
                await asyncio.sleep(0.01)
    finally:
        await scheduler.stop()

    assert executor.executed == [automation.id]


async def test_resume_catches_up_a_missed_run_and_persists_the_next_one(
    automation_repository: SQLAutomationRepository,
) -> None:
    missed_at = datetime.now(UTC) - timedelta(minutes=5)
    automation = await automation_repository.save(
        Automation.create(
            owner_id="owner",
            target=SessionTarget(uuid4()),
            schedule=IntervalSchedule(every=timedelta(hours=1)),
            action=PromptAction("Drink water"),
            origin=AutomationOrigin(uuid4()),
            next_run_at=missed_at,
        )
    )
    executor = RecordingExecutor()
    scheduler = _scheduler(automation_repository, executor)
    service = AutomationService(
        automation_repository,
        AcceptAllTargets(),
        InProcessAutomationScheduler(scheduler),
    )

    await scheduler.start()
    try:
        await service.resume()
        async with asyncio.timeout(1):
            while (
                stored := await automation_repository.find_by_id(automation.id)
            ) is not None and stored.next_run_at == missed_at:
                await asyncio.sleep(0.01)
    finally:
        await scheduler.stop()

    assert executor.executed == [automation.id]
    assert stored is not None
    assert stored.next_run_at == missed_at + timedelta(hours=1)


def _scheduler(
    repository: SQLAutomationRepository,
    executor: RecordingExecutor,
) -> Scheduler[UUID]:
    return Scheduler(AutomationJobRunner(AutomationExecution(repository, executor)))
