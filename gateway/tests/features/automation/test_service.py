from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from features.automation.fakes import (
    AcceptAllTargets,
    ImmediateTransaction,
    RecordingScheduler,
)
from gateway.features.automation.application import (
    AutomationService,
    AutomationTargetResolver,
)
from gateway.features.automation.domain import (
    AtSchedule,
    AutomationNotFoundError,
    AutomationTarget,
    IntervalSchedule,
    PromptAction,
    SessionTarget,
)
from gateway.features.automation.infrastructure.repository import (
    SQLAutomationRepository,
)

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
    )
    await automation_service.create(
        _OTHER_OWNER,
        target=SessionTarget(uuid4()),
        schedule=AtSchedule(run_at=datetime(2027, 1, 2, tzinfo=UTC)),
        action=PromptAction("Hidden"),
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
    )
    second = await automation_service.create(
        _OWNER,
        target=SessionTarget(uuid4()),
        schedule=AtSchedule(run_at=datetime(2027, 1, 2, tzinfo=UTC)),
        action=PromptAction("From the office"),
    )

    listed = await automation_service.list(_OWNER)

    assert {automation.id for automation in listed} == {first.id, second.id}


async def test_create_persists_the_first_run_and_arms_it(
    automation_service: AutomationService,
    recording_scheduler: RecordingScheduler,
) -> None:
    created = await automation_service.create(
        _OWNER,
        target=SessionTarget(uuid4()),
        schedule=IntervalSchedule(every=timedelta(hours=1)),
        action=PromptAction("Drink water"),
    )

    fetched = await automation_service.get(created.id, _OWNER)

    assert fetched.next_run_at == recording_scheduler.next_run_at
    assert recording_scheduler.armed == {created.id: recording_scheduler.next_run_at}


async def test_create_validates_the_target_before_scheduling(
    automation_repository: SQLAutomationRepository,
    recording_scheduler: RecordingScheduler,
) -> None:
    class RejectAllTargets(AutomationTargetResolver):
        async def require(self, target: AutomationTarget) -> None:
            raise LookupError(target)

    service = AutomationService(
        automation_repository,
        RejectAllTargets(),
        recording_scheduler,
        ImmediateTransaction(),
    )

    with pytest.raises(LookupError):
        await service.create(
            _OWNER,
            target=SessionTarget(uuid4()),
            schedule=AtSchedule(run_at=datetime(2027, 1, 1, tzinfo=UTC)),
            action=PromptAction("Unreachable"),
        )
    assert await service.list(_OWNER) == ()
    assert recording_scheduler.armed == {}


async def test_get_raises_for_an_automation_of_another_owner(
    automation_service: AutomationService,
) -> None:
    automation = await automation_service.create(
        _OWNER,
        target=SessionTarget(uuid4()),
        schedule=AtSchedule(run_at=datetime(2027, 1, 1, tzinfo=UTC)),
        action=PromptAction("Private"),
    )

    with pytest.raises(AutomationNotFoundError):
        await automation_service.get(automation.id, _OTHER_OWNER)


async def test_get_raises_for_an_unknown_automation_id(
    automation_service: AutomationService,
) -> None:
    with pytest.raises(AutomationNotFoundError):
        await automation_service.get(uuid4(), _OWNER)


async def test_update_replaces_schedule_action_and_name_but_keeps_identity(
    automation_service: AutomationService,
    recording_scheduler: RecordingScheduler,
) -> None:
    target = SessionTarget(uuid4())
    created = await automation_service.create(
        _OWNER,
        target=target,
        schedule=AtSchedule(run_at=datetime(2027, 1, 1, tzinfo=UTC)),
        action=PromptAction("Stretch"),
        name="Stretch",
    )
    recording_scheduler.next_run_at = datetime(2027, 2, 1, tzinfo=UTC)

    await automation_service.update(
        created.id,
        _OWNER,
        schedule=IntervalSchedule(every=timedelta(hours=1)),
        action=PromptAction("Stretch more"),
        name="Stretch more",
    )
    updated = await automation_service.get(created.id, _OWNER)

    assert updated.created_at == created.created_at
    assert updated.owner_id == _OWNER
    assert updated.target == target
    assert updated.schedule == IntervalSchedule(every=timedelta(hours=1))
    assert updated.action == PromptAction("Stretch more")
    assert updated.name == "Stretch more"
    assert updated.next_run_at == datetime(2027, 2, 1, tzinfo=UTC)
    assert recording_scheduler.armed == {created.id: updated.next_run_at}


async def test_update_refuses_to_touch_an_automation_of_another_owner(
    automation_service: AutomationService,
) -> None:
    automation = await automation_service.create(
        _OWNER,
        target=SessionTarget(uuid4()),
        schedule=AtSchedule(run_at=datetime(2027, 1, 1, tzinfo=UTC)),
        action=PromptAction("Private"),
    )

    with pytest.raises(AutomationNotFoundError):
        await automation_service.update(
            automation.id,
            _OTHER_OWNER,
            schedule=AtSchedule(run_at=datetime(2027, 2, 1, tzinfo=UTC)),
            action=PromptAction("Hijacked"),
        )


async def test_delete_removes_and_disarms_the_automation(
    automation_service: AutomationService,
    recording_scheduler: RecordingScheduler,
) -> None:
    automation = await automation_service.create(
        _OWNER,
        target=SessionTarget(uuid4()),
        schedule=AtSchedule(run_at=datetime(2027, 1, 1, tzinfo=UTC)),
        action=PromptAction("Once"),
    )

    await automation_service.delete(automation.id, _OWNER)

    assert await automation_service.list(_OWNER) == ()
    assert recording_scheduler.armed == {}


async def test_delete_refuses_to_touch_an_automation_of_another_owner(
    automation_service: AutomationService,
) -> None:
    automation = await automation_service.create(
        _OWNER,
        target=SessionTarget(uuid4()),
        schedule=AtSchedule(run_at=datetime(2027, 1, 1, tzinfo=UTC)),
        action=PromptAction("Private"),
    )

    with pytest.raises(AutomationNotFoundError):
        await automation_service.delete(automation.id, _OTHER_OWNER)


async def test_resume_arms_every_persisted_automation_at_its_stored_next_run(
    automation_repository: SQLAutomationRepository,
    automation_service: AutomationService,
    recording_scheduler: RecordingScheduler,
) -> None:
    first = await automation_service.create(
        _OWNER,
        target=SessionTarget(uuid4()),
        schedule=IntervalSchedule(every=timedelta(hours=1)),
        action=PromptAction("First"),
    )
    recording_scheduler.next_run_at = datetime(2027, 3, 1, tzinfo=UTC)
    second = await automation_service.create(
        _OTHER_OWNER,
        target=SessionTarget(uuid4()),
        schedule=IntervalSchedule(every=timedelta(hours=2)),
        action=PromptAction("Second"),
    )
    restarted = RecordingScheduler()

    await AutomationService(
        automation_repository,
        AcceptAllTargets(),
        restarted,
        ImmediateTransaction(),
    ).resume()

    assert restarted.armed == {
        first.id: first.next_run_at,
        second.id: second.next_run_at,
    }
