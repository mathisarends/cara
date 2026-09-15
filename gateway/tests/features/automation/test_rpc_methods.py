from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from gateway.features.automation.application import AutomationService
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
    SessionAutomationTarget,
    UpdateAutomationParams,
)

_OWNER = "owner"


async def test_create_list_and_get_a_reminder_automation(
    automation_service: AutomationService,
) -> None:
    target = SessionAutomationTarget(kind="session", session_id=uuid4())
    payload = ReminderAutomationPayload(
        kind="reminder",
        instruction="Drink water",
        created_from_turn_id=uuid4(),
    )

    created = await create_automation(
        CreateAutomationParams(
            owner_id=_OWNER,
            target=target,
            schedule=IntervalSchedule(every_seconds=1800, run_immediately=False),
            payload=payload,
            name="Hydration",
        ),
        automation_service,
    )
    listed = await list_automations(
        ListAutomationsParams(owner_id=_OWNER),
        automation_service,
    )
    fetched = await get_automation(
        GetAutomationParams(owner_id=_OWNER, automation_id=created.id),
        automation_service,
    )

    assert listed.automations == (created,)
    assert fetched == created
    assert fetched.owner_id == _OWNER
    assert fetched.name == "Hydration"
    assert fetched.schedule == IntervalSchedule(
        every_seconds=1800,
        run_immediately=False,
    )
    assert fetched.target == target
    assert fetched.payload == payload
    assert fetched.created_at <= datetime.now(UTC)


async def test_update_and_delete_an_automation(
    automation_service: AutomationService,
) -> None:
    payload = ReminderAutomationPayload(
        kind="reminder",
        instruction="Stand up",
        created_from_turn_id=uuid4(),
    )
    created = await create_automation(
        CreateAutomationParams(
            owner_id=_OWNER,
            target=SessionAutomationTarget(kind="session", session_id=uuid4()),
            schedule=IntervalSchedule(every_seconds=900, run_immediately=False),
            payload=payload,
            name="Stand up",
        ),
        automation_service,
    )

    updated = await update_automation(
        UpdateAutomationParams(
            owner_id=_OWNER,
            automation_id=created.id,
            schedule=CronSchedule(expression="0 9 * * *", timezone="Europe/Berlin"),
            payload=payload.model_copy(update={"instruction": "Stand up now"}),
            name="Morning stand up",
        ),
        automation_service,
    )
    assert updated.id == created.id
    assert updated.target == created.target
    assert updated.schedule == CronSchedule(
        expression="0 9 * * *",
        timezone="Europe/Berlin",
    )
    assert updated.payload.instruction == "Stand up now"
    assert updated.name == "Morning stand up"

    deleted = await delete_automation(
        DeleteAutomationParams(owner_id=_OWNER, automation_id=created.id),
        automation_service,
    )
    assert deleted.deleted == created.id
    listed = await list_automations(
        ListAutomationsParams(owner_id=_OWNER),
        automation_service,
    )
    assert listed.automations == ()


async def test_rejects_an_empty_owner_id() -> None:
    with pytest.raises(ValidationError):
        ListAutomationsParams(owner_id="")


async def test_rejects_an_unknown_cron_timezone() -> None:
    with pytest.raises(ValidationError):
        CronSchedule(expression="0 9 * * *", timezone="Mars/Olympus_Mons")
