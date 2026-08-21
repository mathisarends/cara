from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from gateway.features.automation.application import AutomationService
from gateway.features.automation.domain import (
    AutomationEnvelope,
    AutomationNotFoundError,
    ReminderPayload,
    SessionAutomationTarget,
)
from scheduler import MemoryJobStore, ScheduledRun, Scheduler


async def _runner(run: ScheduledRun[AutomationEnvelope]) -> None:
    pass


def _reminder(session_id: UUID, message: str) -> AutomationEnvelope:
    return AutomationEnvelope(
        schema_version=1,
        target=SessionAutomationTarget(kind="session", session_id=session_id),
        payload=ReminderPayload(
            kind="reminder",
            message=message,
            created_from_turn_id=uuid4(),
        ),
    )


async def test_service_limits_list_and_get_to_the_requested_session() -> None:
    scheduler = Scheduler(_runner, MemoryJobStore[AutomationEnvelope]())
    service = AutomationService(scheduler)
    session_id = uuid4()
    other_session_id = uuid4()
    visible = await scheduler.at(
        datetime(2027, 1, 1, tzinfo=UTC),
        payload=_reminder(session_id, "Visible"),
        job_id="visible",
    )
    await scheduler.at(
        datetime(2027, 1, 2, tzinfo=UTC),
        payload=_reminder(other_session_id, "Hidden"),
        job_id="hidden",
    )

    assert await service.list_for_session(session_id) == (visible,)
    assert await service.get_for_session("visible", session_id) == visible
    with pytest.raises(AutomationNotFoundError):
        await service.get_for_session("hidden", session_id)
