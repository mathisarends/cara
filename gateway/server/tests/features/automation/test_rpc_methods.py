from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from pydantic import ValidationError

from gateway.features.automation.application import AutomationService
from gateway.features.automation.domain import (
    AutomationEnvelope,
    ReminderPayload,
    SessionAutomationTarget,
)
from gateway.features.automation.presentation.rpc_methods import AutomationRpcMethods
from gateway.features.automation.presentation.schemas import (
    CreateAutomationParams,
    CronSchedule,
    DeleteAutomationParams,
    GetAutomationParams,
    IntervalSchedule,
    ListAutomationsParams,
    ReminderAutomationPayload,
    UpdateAutomationParams,
)
from scheduler import MemoryJobStore, ScheduledRun, Scheduler


async def _runner(run: ScheduledRun[AutomationEnvelope]) -> None:
    pass


async def test_rpc_lists_and_gets_typed_automations() -> None:
    scheduler = Scheduler(_runner, MemoryJobStore[AutomationEnvelope]())
    methods = AutomationRpcMethods(AutomationService(scheduler))
    session_id = uuid4()
    await scheduler.interval(
        every=timedelta(minutes=30),
        run_immediately=False,
        payload=AutomationEnvelope(
            schema_version=2,
            target=SessionAutomationTarget(kind="session", session_id=session_id),
            payload=ReminderPayload(
                kind="reminder",
                instruction="Drink water",
                created_from_turn_id=uuid4(),
            ),
        ),
        job_id="drink-water",
        name="Hydration",
    )

    listed = await methods.list_automations(
        ListAutomationsParams(session_id=session_id)
    )
    fetched = await methods.get_automation(
        GetAutomationParams(
            session_id=session_id,
            automation_id="drink-water",
        )
    )

    assert listed.automations == (fetched,)
    assert fetched.name == "Hydration"
    assert fetched.schedule.kind == "interval"
    assert fetched.target.session_id == session_id
    assert fetched.payload.kind == "reminder"
    assert fetched.created_at <= datetime.now(UTC)


async def test_rpc_creates_updates_and_deletes_an_automation() -> None:
    scheduler = Scheduler(_runner, MemoryJobStore[AutomationEnvelope]())
    methods = AutomationRpcMethods(AutomationService(scheduler))
    session_id = uuid4()
    payload = ReminderAutomationPayload(
        kind="reminder",
        instruction="Stand up",
        created_from_turn_id=uuid4(),
    )

    created = await methods.create_automation(
        CreateAutomationParams(
            session_id=session_id,
            schedule=IntervalSchedule(every_seconds=900, run_immediately=False),
            payload=payload,
            name="Stand up",
        )
    )
    assert created.schedule == IntervalSchedule(
        every_seconds=900,
        run_immediately=False,
    )
    assert created.target.session_id == session_id

    updated = await methods.update_automation(
        UpdateAutomationParams(
            session_id=session_id,
            automation_id=created.id,
            schedule=CronSchedule(expression="0 9 * * *", timezone="Europe/Berlin"),
            payload=payload.model_copy(update={"instruction": "Stand up now"}),
            name="Morning stand up",
        )
    )
    assert updated.id == created.id
    assert updated.schedule == CronSchedule(
        expression="0 9 * * *",
        timezone="Europe/Berlin",
    )
    assert updated.payload.instruction == "Stand up now"
    assert updated.name == "Morning stand up"

    deleted = await methods.delete_automation(
        DeleteAutomationParams(session_id=session_id, automation_id=created.id)
    )
    assert deleted.deleted == created.id
    listed = await methods.list_automations(
        ListAutomationsParams(session_id=session_id)
    )
    assert listed.automations == ()


async def test_rpc_rejects_an_unknown_cron_timezone() -> None:
    with pytest.raises(ValidationError):
        CronSchedule(expression="0 9 * * *", timezone="Mars/Olympus_Mons")
