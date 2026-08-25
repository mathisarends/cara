from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest

from gateway.features.automation.application import AutomationService
from gateway.features.automation.domain import (
    AutomationEnvelope,
    AutomationNotFoundError,
    ReminderPayload,
    SessionAutomationTarget,
)
from scheduler import At, Interval, MemoryJobStore, ScheduledRun, Scheduler


async def _runner(run: ScheduledRun[AutomationEnvelope]) -> None:
    pass


def _reminder(session_id: UUID, instruction: str) -> AutomationEnvelope:
    return AutomationEnvelope(
        schema_version=2,
        target=SessionAutomationTarget(kind="session", session_id=session_id),
        payload=ReminderPayload(
            kind="reminder",
            instruction=instruction,
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


async def test_service_creates_updates_and_deletes_session_automations() -> None:
    scheduler = Scheduler(_runner, MemoryJobStore[AutomationEnvelope]())
    service = AutomationService(scheduler)
    session_id = uuid4()

    created = await service.create_for_session(
        session_id,
        trigger=At(when=datetime(2027, 1, 1, tzinfo=UTC)),
        payload=_reminder(session_id, "Stretch").payload,
        name="Stretch",
    )
    assert await service.list_for_session(session_id) == (created,)

    updated = await service.update_for_session(
        created.id,
        session_id,
        trigger=Interval(every=timedelta(hours=1), run_immediately=False),
        payload=_reminder(session_id, "Stretch more").payload,
        name="Stretch more",
    )
    assert updated.id == created.id
    assert updated.created_at == created.created_at
    assert updated.trigger == Interval(every=timedelta(hours=1), run_immediately=False)
    assert updated.payload.payload.instruction == "Stretch more"
    assert updated.payload.target == created.payload.target

    await service.delete_for_session(created.id, session_id)
    assert await service.list_for_session(session_id) == ()


async def test_service_refuses_to_touch_automations_of_another_session() -> None:
    scheduler = Scheduler(_runner, MemoryJobStore[AutomationEnvelope]())
    service = AutomationService(scheduler)
    session_id = uuid4()
    other_session_id = uuid4()
    job = await service.create_for_session(
        session_id,
        trigger=At(when=datetime(2027, 1, 1, tzinfo=UTC)),
        payload=_reminder(session_id, "Private").payload,
    )

    with pytest.raises(AutomationNotFoundError):
        await service.update_for_session(
            job.id,
            other_session_id,
            trigger=At(when=datetime(2027, 2, 1, tzinfo=UTC)),
            payload=_reminder(session_id, "Hijacked").payload,
        )
    with pytest.raises(AutomationNotFoundError):
        await service.delete_for_session(job.id, other_session_id)

    assert await service.get_for_session(job.id, session_id) == job
