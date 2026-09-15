from datetime import timedelta
from uuid import uuid4

import pytest

from features.alarm.fakes import (
    DAILY_AT_SIX,
    NEXT_WAKE,
    NOW,
    AcceptAllTargets,
    FixedClock,
    RecordingScheduler,
    find_alarm,
    make_alarm,
    once_at,
    save_alarm,
)
from gateway.features.alarm.application import (
    AlarmService,
    AlarmStore,
    AlarmTargetResolver,
)
from gateway.features.alarm.domain import (
    AlarmNotFoundError,
    AlarmPhase,
    AlarmRepository,
    AlarmRoutine,
    AlarmStateError,
    AlarmTarget,
    OccurrenceState,
    SessionTarget,
)
from gateway.shared import UnitOfWork

_OWNER = "owner"
_OTHER_OWNER = "someone-else"


async def test_create_persists_and_arms_the_first_run(
    alarm_service: AlarmService,
    recording_scheduler: RecordingScheduler,
) -> None:
    created = await _create(alarm_service)

    fetched = await alarm_service.get(created.id, _OWNER)
    run = recording_scheduler.armed[created.id]

    assert fetched.occurrence is not None
    assert fetched.occurrence.wake_at == NEXT_WAKE
    assert run is not None
    assert run.phase is AlarmPhase.PRE_WAKE


async def test_create_validates_the_target_before_scheduling(
    alarm_store: AlarmStore,
    clock: FixedClock,
    recording_scheduler: RecordingScheduler,
) -> None:
    class RejectAllTargets(AlarmTargetResolver):
        async def require(self, target: AlarmTarget) -> None:
            raise LookupError(target)

    service = AlarmService(alarm_store, RejectAllTargets(), clock)

    with pytest.raises(LookupError):
        await _create(service)
    assert await service.list(_OWNER) == ()
    assert recording_scheduler.armed == {}


async def test_alarms_are_scoped_to_their_owner(alarm_service: AlarmService) -> None:
    mine = await _create(alarm_service)
    theirs = await _create(alarm_service, owner_id=_OTHER_OWNER)

    assert [alarm.id for alarm in await alarm_service.list(_OWNER)] == [mine.id]
    for command in (
        alarm_service.get(theirs.id, _OWNER),
        alarm_service.delete(theirs.id, _OWNER),
        alarm_service.dismiss(theirs.id, _OWNER),
        alarm_service.get(uuid4(), _OWNER),
    ):
        with pytest.raises(AlarmNotFoundError):
            await command


async def test_update_replaces_the_alarm_but_keeps_its_identity(
    alarm_service: AlarmService,
    recording_scheduler: RecordingScheduler,
) -> None:
    created = await _create(alarm_service, name="Werktags")
    wake_at = NOW + timedelta(hours=8)

    updated = await alarm_service.update(
        created.id,
        _OWNER,
        recurrence=once_at(wake_at),
        routine=AlarmRoutine("wake-up", note="ohne Musik"),
        name="Nap",
    )

    assert updated.created_at == created.created_at
    assert updated.target == created.target
    assert updated.routine.note == "ohne Musik"
    assert updated.pre_wake_lead is None
    assert updated.occurrence is not None
    assert updated.occurrence.wake_at == wake_at
    armed = recording_scheduler.armed[created.id]
    assert armed is not None
    assert armed.phase is AlarmPhase.WAKE


async def test_delete_removes_and_disarms_the_alarm(
    alarm_service: AlarmService,
    recording_scheduler: RecordingScheduler,
) -> None:
    alarm = await _create(alarm_service)

    await alarm_service.delete(alarm.id, _OWNER)

    assert await alarm_service.list(_OWNER) == ()
    assert recording_scheduler.armed == {}


async def test_set_enabled_and_skip_next_rearm_the_alarm(
    alarm_service: AlarmService,
    recording_scheduler: RecordingScheduler,
) -> None:
    alarm = await _create(alarm_service)

    disabled = await alarm_service.set_enabled(alarm.id, _OWNER, False)
    assert disabled.occurrence is None
    assert recording_scheduler.armed[alarm.id] is None

    await alarm_service.set_enabled(alarm.id, _OWNER, True)
    skipped = await alarm_service.skip_next(alarm.id, _OWNER)

    assert skipped.occurrence is not None
    assert skipped.occurrence.wake_at == NEXT_WAKE + timedelta(days=1)
    armed = recording_scheduler.armed[alarm.id]
    assert armed is not None
    assert armed.wake_at == NEXT_WAKE + timedelta(days=1)


async def test_snooze_requires_a_ringing_alarm(alarm_service: AlarmService) -> None:
    alarm = await _create(alarm_service)

    with pytest.raises(AlarmStateError):
        await alarm_service.snooze(alarm.id, _OWNER, timedelta(minutes=9))


async def test_snooze_and_dismiss_a_ringing_one_time_alarm(
    alarm_repositories: UnitOfWork[AlarmRepository],
    alarm_service: AlarmService,
    clock: FixedClock,
    recording_scheduler: RecordingScheduler,
) -> None:
    alarm = make_alarm(recurrence=once_at(NEXT_WAKE), pre_wake_lead=None)
    run = alarm.next_due_run(NEXT_WAKE)
    assert run is not None
    alarm.start_run(run, NEXT_WAKE)
    await save_alarm(alarm_repositories, alarm)
    clock.current = NEXT_WAKE + timedelta(minutes=1)

    snoozed = await alarm_service.snooze(alarm.id, _OWNER, timedelta(minutes=9))
    dismissed = await alarm_service.dismiss(alarm.id, _OWNER)

    assert snoozed.occurrence is not None
    assert snoozed.occurrence.state is OccurrenceState.SNOOZED
    assert snoozed.occurrence.snooze_count == 1
    assert dismissed is None
    assert await find_alarm(alarm_repositories, alarm.id) is None
    assert recording_scheduler.armed == {}


async def test_resume_arms_every_persisted_alarm(
    alarm_repositories: UnitOfWork[AlarmRepository],
    alarm_service: AlarmService,
    clock: FixedClock,
) -> None:
    first = await _create(alarm_service)
    second = await _create(alarm_service, owner_id=_OTHER_OWNER)
    restarted = RecordingScheduler()

    await AlarmService(
        AlarmStore(alarm_repositories, restarted),
        AcceptAllTargets(),
        clock,
    ).resume()

    assert restarted.armed.keys() == {first.id, second.id}


async def _create(
    service: AlarmService,
    *,
    owner_id: str = _OWNER,
    name: str | None = None,
):
    return await service.create(
        owner_id,
        target=SessionTarget(uuid4()),
        recurrence=DAILY_AT_SIX,
        routine=AlarmRoutine("wake-up"),
        pre_wake_lead=timedelta(minutes=30),
        name=name,
    )
