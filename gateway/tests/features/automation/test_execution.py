from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from features.automation.fakes import RecordingExecutor
from gateway.features.automation.application import AutomationExecution
from gateway.features.automation.domain import (
    Automation,
    AutomationOrigin,
    IntervalSchedule,
    PromptAction,
    SessionTarget,
)
from gateway.features.automation.infrastructure.repository import (
    SQLAutomationRepository,
)

_SCHEDULED_FOR = datetime(2027, 1, 1, 9, tzinfo=UTC)
_NEXT_RUN_AT = _SCHEDULED_FOR + timedelta(hours=1)


async def test_a_recurring_run_executes_and_persists_the_next_run(
    automation_repository: SQLAutomationRepository,
) -> None:
    automation = await automation_repository.save(_automation())
    executor = RecordingExecutor()

    await AutomationExecution(automation_repository, executor).run(
        automation.id,
        scheduled_for=_SCHEDULED_FOR,
        next_run_at=_NEXT_RUN_AT,
    )

    stored = await automation_repository.find_by_id(automation.id)
    assert executor.executed == [automation.id]
    assert stored is not None
    assert stored.next_run_at == _NEXT_RUN_AT


async def test_the_final_run_removes_the_automation(
    automation_repository: SQLAutomationRepository,
) -> None:
    automation = await automation_repository.save(_automation())
    executor = RecordingExecutor()

    await AutomationExecution(automation_repository, executor).run(
        automation.id,
        scheduled_for=_SCHEDULED_FOR,
        next_run_at=None,
    )

    assert executor.executed == [automation.id]
    assert await automation_repository.find_by_id(automation.id) is None


async def test_a_failed_run_still_advances_and_reraises(
    automation_repository: SQLAutomationRepository,
) -> None:
    automation = await automation_repository.save(_automation())
    executor = RecordingExecutor(RuntimeError("boom"))

    with pytest.raises(RuntimeError, match="boom"):
        await AutomationExecution(automation_repository, executor).run(
            automation.id,
            scheduled_for=_SCHEDULED_FOR,
            next_run_at=_NEXT_RUN_AT,
        )

    stored = await automation_repository.find_by_id(automation.id)
    assert stored is not None
    assert stored.next_run_at == _NEXT_RUN_AT


async def test_a_run_for_a_deleted_automation_is_ignored(
    automation_repository: SQLAutomationRepository,
) -> None:
    executor = RecordingExecutor()

    await AutomationExecution(automation_repository, executor).run(
        uuid4(),
        scheduled_for=_SCHEDULED_FOR,
        next_run_at=_NEXT_RUN_AT,
    )

    assert executor.executed == []


def _automation() -> Automation:
    return Automation.create(
        owner_id="owner",
        target=SessionTarget(uuid4()),
        schedule=IntervalSchedule(every=timedelta(hours=1)),
        action=PromptAction("Drink water"),
        origin=AutomationOrigin(uuid4()),
        next_run_at=_SCHEDULED_FOR,
    )
