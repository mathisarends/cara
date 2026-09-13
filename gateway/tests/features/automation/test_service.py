from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from gateway.features.automation.application import SessionAutomationService
from gateway.features.automation.domain import (
    AtSchedule,
    AutomationNotFoundError,
    AutomationOrigin,
    IntervalSchedule,
    PromptAction,
)


async def test_create_and_list_are_scoped_to_the_session(
    automation_service: SessionAutomationService,
) -> None:
    session_id = uuid4()
    other_session_id = uuid4()
    visible = await automation_service.create(
        session_id,
        schedule=AtSchedule(run_at=datetime(2027, 1, 1, tzinfo=UTC)),
        action=PromptAction("Visible"),
        origin=AutomationOrigin(uuid4()),
    )
    await automation_service.create(
        other_session_id,
        schedule=AtSchedule(run_at=datetime(2027, 1, 2, tzinfo=UTC)),
        action=PromptAction("Hidden"),
        origin=AutomationOrigin(uuid4()),
    )

    listed = await automation_service.list(session_id)

    assert [automation.id for automation in listed] == [visible.id]


async def test_get_raises_for_an_automation_outside_the_session(
    automation_service: SessionAutomationService,
) -> None:
    session_id = uuid4()
    other_session_id = uuid4()
    automation = await automation_service.create(
        session_id,
        schedule=AtSchedule(run_at=datetime(2027, 1, 1, tzinfo=UTC)),
        action=PromptAction("Private"),
        origin=AutomationOrigin(uuid4()),
    )

    with pytest.raises(AutomationNotFoundError):
        await automation_service.get(automation.id, other_session_id)


async def test_get_raises_for_an_unknown_automation_id(
    automation_service: SessionAutomationService,
) -> None:
    with pytest.raises(AutomationNotFoundError):
        await automation_service.get("missing", uuid4())


async def test_update_replaces_schedule_action_and_name_but_keeps_identity(
    automation_service: SessionAutomationService,
) -> None:
    session_id = uuid4()
    created = await automation_service.create(
        session_id,
        schedule=AtSchedule(run_at=datetime(2027, 1, 1, tzinfo=UTC)),
        action=PromptAction("Stretch"),
        origin=AutomationOrigin(uuid4()),
        name="Stretch",
    )

    updated = await automation_service.update(
        created.id,
        session_id,
        schedule=IntervalSchedule(every=timedelta(hours=1)),
        action=PromptAction("Stretch more"),
        origin=AutomationOrigin(uuid4()),
        name="Stretch more",
    )

    assert updated.id == created.id
    assert updated.created_at == created.created_at
    assert updated.schedule == IntervalSchedule(every=timedelta(hours=1))
    assert updated.action == PromptAction("Stretch more")
    assert updated.name == "Stretch more"


async def test_update_refuses_to_touch_an_automation_of_another_session(
    automation_service: SessionAutomationService,
) -> None:
    session_id = uuid4()
    other_session_id = uuid4()
    automation = await automation_service.create(
        session_id,
        schedule=AtSchedule(run_at=datetime(2027, 1, 1, tzinfo=UTC)),
        action=PromptAction("Private"),
        origin=AutomationOrigin(uuid4()),
    )

    with pytest.raises(AutomationNotFoundError):
        await automation_service.update(
            automation.id,
            other_session_id,
            schedule=AtSchedule(run_at=datetime(2027, 2, 1, tzinfo=UTC)),
            action=PromptAction("Hijacked"),
            origin=AutomationOrigin(uuid4()),
        )


async def test_delete_removes_the_automation(
    automation_service: SessionAutomationService,
) -> None:
    session_id = uuid4()
    automation = await automation_service.create(
        session_id,
        schedule=AtSchedule(run_at=datetime(2027, 1, 1, tzinfo=UTC)),
        action=PromptAction("Once"),
        origin=AutomationOrigin(uuid4()),
    )

    await automation_service.delete(automation.id, session_id)

    assert await automation_service.list(session_id) == ()


async def test_delete_refuses_to_touch_an_automation_of_another_session(
    automation_service: SessionAutomationService,
) -> None:
    session_id = uuid4()
    other_session_id = uuid4()
    automation = await automation_service.create(
        session_id,
        schedule=AtSchedule(run_at=datetime(2027, 1, 1, tzinfo=UTC)),
        action=PromptAction("Private"),
        origin=AutomationOrigin(uuid4()),
    )

    with pytest.raises(AutomationNotFoundError):
        await automation_service.delete(automation.id, other_session_id)
