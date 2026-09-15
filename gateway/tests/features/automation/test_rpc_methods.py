from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from gateway.features.automation.application import SessionAutomationService
from gateway.features.automation.presentation.rpc.methods import (
    create_automation,
    delete_automation,
    get_automation,
    list_automations,
    update_automation,
)
from gateway.features.automation.presentation.rpc.models import (
    CreateAutomationParams,
    CronSchedule,
    DeleteAutomationParams,
    GetAutomationParams,
    IntervalSchedule,
    ListAutomationsParams,
    ReminderAutomationPayload,
    UpdateAutomationParams,
)


async def test_create_list_and_get_a_reminder_automation(
    automation_service: SessionAutomationService,
) -> None:
    session_id = uuid4()
    payload = ReminderAutomationPayload(
        kind="reminder",
        instruction="Drink water",
        created_from_turn_id=uuid4(),
    )

    created = await create_automation(
        CreateAutomationParams(
            session_id=session_id,
            schedule=IntervalSchedule(every_seconds=1800, run_immediately=False),
            payload=payload,
            name="Hydration",
        ),
        automation_service,
    )
    listed = await list_automations(
        ListAutomationsParams(session_id=session_id),
        automation_service,
    )
    fetched = await get_automation(
        GetAutomationParams(session_id=session_id, automation_id=created.id),
        automation_service,
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


async def test_update_and_delete_an_automation(
    automation_service: SessionAutomationService,
) -> None:
    session_id = uuid4()
    payload = ReminderAutomationPayload(
        kind="reminder",
        instruction="Stand up",
        created_from_turn_id=uuid4(),
    )
    created = await create_automation(
        CreateAutomationParams(
            session_id=session_id,
            schedule=IntervalSchedule(every_seconds=900, run_immediately=False),
            payload=payload,
            name="Stand up",
        ),
        automation_service,
    )

    updated = await update_automation(
        UpdateAutomationParams(
            session_id=session_id,
            automation_id=created.id,
            schedule=CronSchedule(expression="0 9 * * *", timezone="Europe/Berlin"),
            payload=payload.model_copy(update={"instruction": "Stand up now"}),
            name="Morning stand up",
        ),
        automation_service,
    )
    assert updated.id == created.id
    assert updated.schedule == CronSchedule(
        expression="0 9 * * *",
        timezone="Europe/Berlin",
    )
    assert updated.payload.instruction == "Stand up now"
    assert updated.name == "Morning stand up"

    deleted = await delete_automation(
        DeleteAutomationParams(session_id=session_id, automation_id=created.id),
        automation_service,
    )
    assert deleted.deleted == created.id
    listed = await list_automations(
        ListAutomationsParams(session_id=session_id),
        automation_service,
    )
    assert listed.automations == ()


async def test_rejects_an_unknown_cron_timezone() -> None:
    with pytest.raises(ValidationError):
        CronSchedule(expression="0 9 * * *", timezone="Mars/Olympus_Mons")
