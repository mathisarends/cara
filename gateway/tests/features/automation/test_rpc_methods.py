from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from gateway.features.automation.application import SessionAutomationService
from gateway.features.automation.presentation.rpc.handler import AutomationRpcMethods
from gateway.features.automation.presentation.rpc.schemas import (
    CreateAutomationParams,
    CronSchedule,
    DeleteAutomationParams,
    GetAutomationParams,
    IntervalSchedule,
    ListAutomationsParams,
    ReminderAutomationPayload,
    UpdateAutomationParams,
)


@pytest.fixture
def methods(automation_service: SessionAutomationService) -> AutomationRpcMethods:
    return AutomationRpcMethods(automation_service)


async def test_create_list_and_get_a_reminder_automation(
    methods: AutomationRpcMethods,
) -> None:
    session_id = uuid4()
    payload = ReminderAutomationPayload(
        kind="reminder",
        instruction="Drink water",
        created_from_turn_id=uuid4(),
    )

    created = await methods.create_automation(
        CreateAutomationParams(
            session_id=session_id,
            schedule=IntervalSchedule(every_seconds=1800, run_immediately=False),
            payload=payload,
            name="Hydration",
        )
    )
    listed = await methods.list_automations(
        ListAutomationsParams(session_id=session_id)
    )
    fetched = await methods.get_automation(
        GetAutomationParams(session_id=session_id, automation_id=created.id)
    )

    assert listed.automations == (created,)
    assert fetched == created
    assert fetched.name == "Hydration"
    assert fetched.schedule == IntervalSchedule(
        every_seconds=1800,
        run_immediately=False,
    )
    assert fetched.target.session_id == session_id
    assert fetched.payload == payload
    assert fetched.created_at <= datetime.now(UTC)


async def test_update_and_delete_an_automation(methods: AutomationRpcMethods) -> None:
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


async def test_rejects_an_unknown_cron_timezone() -> None:
    with pytest.raises(ValidationError):
        CronSchedule(expression="0 9 * * *", timezone="Mars/Olympus_Mons")
