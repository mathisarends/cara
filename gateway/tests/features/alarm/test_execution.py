from datetime import timedelta

import pytest

from features.alarm.fakes import (
    NEXT_WAKE,
    FixedClock,
    RecordingExecutor,
    RecordingScheduler,
    make_alarm,
    once_at,
)
from gateway.features.alarm.application import AlarmExecution, AlarmStore
from gateway.features.alarm.domain import (
    ACTIVE_TIMEOUT,
    Alarm,
    AlarmPhase,
    AlarmRoutine,
    DueRun,
    OccurrenceState,
)
from gateway.features.alarm.infrastructure.repository import SQLAlarmRepository


async def test_a_due_wake_run_is_stored_as_active_before_it_executes(
    alarm_repository: SQLAlarmRepository,
    alarm_store: AlarmStore,
    clock: FixedClock,
    recording_scheduler: RecordingScheduler,
) -> None:
    alarm = await alarm_repository.save(make_alarm(pre_wake_lead=None))
    executor = RecordingExecutor(alarm_repository)
    run = _run(alarm, NEXT_WAKE)
    clock.current = NEXT_WAKE

    await AlarmExecution(alarm_store, executor, clock).run(run)

    assert executor.executed == [run]
    assert [occurrence.state for occurrence in executor.stored if occurrence] == [
        OccurrenceState.ACTIVE
    ]
    assert recording_scheduler.armed == {alarm.id: None}


async def test_a_failing_routine_is_not_run_again(
    alarm_repository: SQLAlarmRepository,
    alarm_store: AlarmStore,
    clock: FixedClock,
) -> None:
    alarm = await alarm_repository.save(make_alarm(pre_wake_lead=None))
    executor = RecordingExecutor(error=RuntimeError("speaker offline"))
    run = _run(alarm, NEXT_WAKE)
    clock.current = NEXT_WAKE
    execution = AlarmExecution(alarm_store, executor, clock)

    await execution.run(run)
    await execution.run(run)

    stored = await alarm_repository.find_by_id(alarm.id)
    assert executor.executed == [run]
    assert stored is not None
    assert stored.occurrence is not None
    assert stored.occurrence.state is OccurrenceState.ACTIVE


async def test_a_run_made_stale_by_an_update_does_nothing(
    alarm_repository: SQLAlarmRepository,
    alarm_store: AlarmStore,
    clock: FixedClock,
) -> None:
    alarm = make_alarm(pre_wake_lead=None)
    stale = _run(alarm, NEXT_WAKE)
    alarm.update(
        recurrence=once_at(NEXT_WAKE + timedelta(hours=1)),
        routine=AlarmRoutine("wake-up"),
        now=clock.current,
    )
    await alarm_repository.save(alarm)
    executor = RecordingExecutor()
    clock.current = NEXT_WAKE

    await AlarmExecution(alarm_store, executor, clock).run(stale)

    assert executor.executed == []


async def test_a_run_for_a_dismissed_occurrence_does_nothing(
    alarm_repository: SQLAlarmRepository,
    alarm_store: AlarmStore,
    clock: FixedClock,
) -> None:
    alarm = make_alarm()
    pre_wake = _run(alarm, clock.current)
    clock.current = pre_wake.due_at
    alarm.start_run(pre_wake, clock.current)
    wake = _run(alarm, clock.current)
    alarm.dismiss(clock.current)
    await alarm_repository.save(alarm)
    executor = RecordingExecutor()
    clock.current = NEXT_WAKE

    await AlarmExecution(alarm_store, executor, clock).run(wake)

    assert executor.executed == []


@pytest.mark.parametrize(
    ("delay", "executed"),
    [(timedelta(minutes=10), True), (timedelta(minutes=20), False)],
)
async def test_a_late_wake_run_only_executes_within_the_grace_period(
    alarm_repository: SQLAlarmRepository,
    alarm_store: AlarmStore,
    clock: FixedClock,
    delay: timedelta,
    executed: bool,
) -> None:
    alarm = await alarm_repository.save(make_alarm(pre_wake_lead=None))
    executor = RecordingExecutor()
    run = _run(alarm, NEXT_WAKE)
    clock.current = NEXT_WAKE + delay

    await AlarmExecution(alarm_store, executor, clock).run(run)

    stored = await alarm_repository.find_by_id(alarm.id)
    assert stored is not None
    assert stored.occurrence is not None
    assert bool(executor.executed) is executed
    if not executed:
        assert stored.occurrence.wake_at == NEXT_WAKE + timedelta(days=1)
        assert stored.occurrence.state is OccurrenceState.UPCOMING


async def test_a_missed_one_time_alarm_is_removed(
    alarm_repository: SQLAlarmRepository,
    alarm_store: AlarmStore,
    clock: FixedClock,
    recording_scheduler: RecordingScheduler,
) -> None:
    alarm = await alarm_repository.save(
        make_alarm(recurrence=once_at(NEXT_WAKE), pre_wake_lead=None)
    )
    run = _run(alarm, NEXT_WAKE)
    recording_scheduler.armed[alarm.id] = run
    clock.current = NEXT_WAKE + timedelta(hours=1)

    await AlarmExecution(alarm_store, RecordingExecutor(), clock).run(run)

    assert await alarm_repository.find_by_id(alarm.id) is None
    assert recording_scheduler.armed == {}


async def test_a_pre_wake_run_after_the_wake_time_skips_to_the_wake_run(
    alarm_repository: SQLAlarmRepository,
    alarm_store: AlarmStore,
    clock: FixedClock,
    recording_scheduler: RecordingScheduler,
) -> None:
    alarm = await alarm_repository.save(make_alarm())
    pre_wake = _run(alarm, clock.current)
    executor = RecordingExecutor()
    clock.current = NEXT_WAKE + timedelta(minutes=2)

    await AlarmExecution(alarm_store, executor, clock).run(pre_wake)

    stored = await alarm_repository.find_by_id(alarm.id)
    assert executor.executed == []
    assert stored is not None
    assert stored.occurrence is not None
    assert stored.occurrence.state is OccurrenceState.PRE_WAKE
    assert recording_scheduler.armed == {
        alarm.id: DueRun(alarm.id, AlarmPhase.WAKE, NEXT_WAKE, NEXT_WAKE)
    }


async def test_an_active_occurrence_closes_after_the_active_timeout(
    alarm_repository: SQLAlarmRepository,
    alarm_store: AlarmStore,
    clock: FixedClock,
) -> None:
    alarm = make_alarm(pre_wake_lead=None)
    alarm.start_run(_run(alarm, NEXT_WAKE), NEXT_WAKE)
    await alarm_repository.save(alarm)
    execution = AlarmExecution(alarm_store, RecordingExecutor(), clock)

    clock.current = NEXT_WAKE + timedelta(minutes=30)
    await execution.expire_due(alarm.id)
    still_active = await alarm_repository.find_by_id(alarm.id)

    clock.current = NEXT_WAKE + ACTIVE_TIMEOUT
    await execution.expire_due(alarm.id)
    closed = await alarm_repository.find_by_id(alarm.id)

    assert still_active is not None
    assert still_active.occurrence is not None
    assert still_active.occurrence.state is OccurrenceState.ACTIVE
    assert closed is not None
    assert closed.occurrence is not None
    assert closed.occurrence.state is OccurrenceState.UPCOMING
    assert closed.occurrence.wake_at == NEXT_WAKE + timedelta(days=1)


def _run(alarm: Alarm, now) -> DueRun:
    run = alarm.next_due_run(now)
    assert run is not None
    return run
