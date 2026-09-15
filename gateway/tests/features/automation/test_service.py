from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from gateway.features.automation.application import (
    AutomationService,
    AutomationTargetResolver,
)
from gateway.features.automation.domain import (
    AtSchedule,
    AutomationNotFoundError,
    AutomationOrigin,
    AutomationTarget,
    IntervalSchedule,
    PromptAction,
    SessionTarget,
)
from gateway.features.automation.infrastructure.codec import AutomationRecord
from gateway.features.automation.infrastructure.scheduler_repository import (
    SchedulerAutomationRepository,
)
from scheduler import Scheduler

_OWNER = "owner"
_OTHER_OWNER = "someone-else"


async def test_create_and_list_are_scoped_to_the_owner(
    automation_service: AutomationService,
) -> None:
    visible = await automation_service.create(
        _OWNER,
        target=SessionTarget(uuid4()),
        schedule=AtSchedule(run_at=datetime(2027, 1, 1, tzinfo=UTC)),
        action=PromptAction("Visible"),
        origin=AutomationOrigin(uuid4()),
    )
    await automation_service.create(
        _OTHER_OWNER,
        target=SessionTarget(uuid4()),
        schedule=AtSchedule(run_at=datetime(2027, 1, 2, tzinfo=UTC)),
        action=PromptAction("Hidden"),
        origin=AutomationOrigin(uuid4()),
    )

    listed = await automation_service.list(_OWNER)

    assert [automation.id for automation in listed] == [visible.id]


async def test_list_spans_every_target_of_the_owner(
    automation_service: AutomationService,
) -> None:
    first = await automation_service.create(
        _OWNER,
        target=SessionTarget(uuid4()),
        schedule=AtSchedule(run_at=datetime(2027, 1, 1, tzinfo=UTC)),
        action=PromptAction("From the kitchen"),
        origin=AutomationOrigin(uuid4()),
    )
    second = await automation_service.create(
        _OWNER,
        target=SessionTarget(uuid4()),
        schedule=AtSchedule(run_at=datetime(2027, 1, 2, tzinfo=UTC)),
        action=PromptAction("From the office"),
        origin=AutomationOrigin(uuid4()),
    )

    listed = await automation_service.list(_OWNER)

    assert {automation.id for automation in listed} == {first.id, second.id}


async def test_create_validates_the_target_before_scheduling(
    automation_scheduler: Scheduler[AutomationRecord],
) -> None:
    class RejectAllTargets(AutomationTargetResolver):
        async def require(self, target: AutomationTarget) -> None:
            raise LookupError(target)

    service = AutomationService(
        SchedulerAutomationRepository(automation_scheduler),
        RejectAllTargets(),
    )

    with pytest.raises(LookupError):
        await service.create(
            _OWNER,
            target=SessionTarget(uuid4()),
            schedule=AtSchedule(run_at=datetime(2027, 1, 1, tzinfo=UTC)),
            action=PromptAction("Unreachable"),
            origin=AutomationOrigin(uuid4()),
        )
    assert await service.list(_OWNER) == ()


async def test_get_raises_for_an_automation_of_another_owner(
    automation_service: AutomationService,
) -> None:
    automation = await automation_service.create(
        _OWNER,
        target=SessionTarget(uuid4()),
        schedule=AtSchedule(run_at=datetime(2027, 1, 1, tzinfo=UTC)),
        action=PromptAction("Private"),
        origin=AutomationOrigin(uuid4()),
    )

    with pytest.raises(AutomationNotFoundError):
        await automation_service.get(automation.id, _OTHER_OWNER)


async def test_get_raises_for_an_unknown_automation_id(
    automation_service: AutomationService,
) -> None:
    with pytest.raises(AutomationNotFoundError):
        await automation_service.get("missing", _OWNER)


async def test_update_replaces_schedule_action_and_name_but_keeps_identity(
    automation_service: AutomationService,
) -> None:
    target = SessionTarget(uuid4())
    created = await automation_service.create(
        _OWNER,
        target=target,
        schedule=AtSchedule(run_at=datetime(2027, 1, 1, tzinfo=UTC)),
        action=PromptAction("Stretch"),
        origin=AutomationOrigin(uuid4()),
        name="Stretch",
    )

    updated = await automation_service.update(
        created.id,
        _OWNER,
        schedule=IntervalSchedule(every=timedelta(hours=1)),
        action=PromptAction("Stretch more"),
        origin=AutomationOrigin(uuid4()),
        name="Stretch more",
    )

    assert updated.id == created.id
    assert updated.created_at == created.created_at
    assert updated.owner_id == _OWNER
    assert updated.target == target
    assert updated.schedule == IntervalSchedule(every=timedelta(hours=1))
    assert updated.action == PromptAction("Stretch more")
    assert updated.name == "Stretch more"


async def test_update_refuses_to_touch_an_automation_of_another_owner(
    automation_service: AutomationService,
) -> None:
    automation = await automation_service.create(
        _OWNER,
        target=SessionTarget(uuid4()),
        schedule=AtSchedule(run_at=datetime(2027, 1, 1, tzinfo=UTC)),
        action=PromptAction("Private"),
        origin=AutomationOrigin(uuid4()),
    )

    with pytest.raises(AutomationNotFoundError):
        await automation_service.update(
            automation.id,
            _OTHER_OWNER,
            schedule=AtSchedule(run_at=datetime(2027, 2, 1, tzinfo=UTC)),
            action=PromptAction("Hijacked"),
            origin=AutomationOrigin(uuid4()),
        )


async def test_delete_removes_the_automation(
    automation_service: AutomationService,
) -> None:
    automation = await automation_service.create(
        _OWNER,
        target=SessionTarget(uuid4()),
        schedule=AtSchedule(run_at=datetime(2027, 1, 1, tzinfo=UTC)),
        action=PromptAction("Once"),
        origin=AutomationOrigin(uuid4()),
    )

    await automation_service.delete(automation.id, _OWNER)

    assert await automation_service.list(_OWNER) == ()


async def test_delete_refuses_to_touch_an_automation_of_another_owner(
    automation_service: AutomationService,
) -> None:
    automation = await automation_service.create(
        _OWNER,
        target=SessionTarget(uuid4()),
        schedule=AtSchedule(run_at=datetime(2027, 1, 1, tzinfo=UTC)),
        action=PromptAction("Private"),
        origin=AutomationOrigin(uuid4()),
    )

    with pytest.raises(AutomationNotFoundError):
        await automation_service.delete(automation.id, _OTHER_OWNER)
