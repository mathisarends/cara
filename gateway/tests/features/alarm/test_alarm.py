from datetime import date, timedelta

import pytest

from features.alarm.fakes import NEXT_WAKE, NOW, make_alarm, once_at
from gateway.features.alarm.domain import (
    ACTIVE_TIMEOUT,
    MISSED_GRACE,
    Alarm,
    AlarmPhase,
    AlarmRoutine,
    AlarmStateError,
    DueRun,
    InvalidAlarmError,
    OccurrenceState,
)

_DAY = timedelta(days=1)


def test_create_schedules_the_next_local_wake_time() -> None:
    alarm = make_alarm()

    assert alarm.occurrence is not None
    assert alarm.occurrence.wake_at == NEXT_WAKE
    assert alarm.occurrence.state is OccurrenceState.UPCOMING
    assert alarm.next_due_run(NOW) == DueRun(
        alarm.id, AlarmPhase.PRE_WAKE, NEXT_WAKE - timedelta(minutes=30), NEXT_WAKE
    )


def test_without_a_lead_the_first_run_is_the_wake_run() -> None:
    alarm = make_alarm(pre_wake_lead=None)

    assert alarm.next_due_run(NOW) == DueRun(
        alarm.id, AlarmPhase.WAKE, NEXT_WAKE, NEXT_WAKE
    )


def test_a_lead_that_no_longer_fits_starts_the_pre_wake_right_away() -> None:
    alarm = make_alarm(recurrence=once_at(NOW + timedelta(minutes=20)))

    run = alarm.next_due_run(NOW)

    assert run is not None
    assert run.phase is AlarmPhase.PRE_WAKE
    assert run.due_at == NOW


def test_an_occurrence_walks_through_pre_wake_wake_snooze_and_dismiss() -> None:
    alarm = make_alarm()
    pre_wake_at = NEXT_WAKE - timedelta(minutes=30)

    alarm.start_run(_due(alarm, pre_wake_at), pre_wake_at)
    assert _state(alarm) is OccurrenceState.PRE_WAKE

    alarm.start_run(_due(alarm, NEXT_WAKE), NEXT_WAKE)
    assert _state(alarm) is OccurrenceState.ACTIVE
    assert alarm.next_due_run(NEXT_WAKE) is None
    assert alarm.expires_at == NEXT_WAKE + ACTIVE_TIMEOUT

    alarm.snooze(timedelta(minutes=9), NEXT_WAKE + timedelta(minutes=1))
    snooze_end = NEXT_WAKE + timedelta(minutes=10)
    assert _state(alarm) is OccurrenceState.SNOOZED
    assert alarm.next_due_run(snooze_end) == DueRun(
        alarm.id, AlarmPhase.SNOOZE_END, snooze_end, NEXT_WAKE
    )

    alarm.start_run(_due(alarm, snooze_end), snooze_end)
    alarm.snooze(timedelta(minutes=5), snooze_end)
    assert alarm.occurrence is not None
    assert alarm.occurrence.snooze_count == 2

    alarm.dismiss(snooze_end + timedelta(minutes=1))
    assert alarm.occurrence is not None
    assert alarm.occurrence.wake_at == NEXT_WAKE + _DAY
    assert _state(alarm) is OccurrenceState.UPCOMING


def test_dismissing_during_pre_wake_ends_the_occurrence_without_a_wake_run() -> None:
    alarm = make_alarm()
    pre_wake_at = NEXT_WAKE - timedelta(minutes=30)
    alarm.start_run(_due(alarm, pre_wake_at), pre_wake_at)

    alarm.dismiss(pre_wake_at + timedelta(minutes=5))

    run = alarm.next_due_run(pre_wake_at + timedelta(minutes=5))
    assert run is not None
    assert run.phase is AlarmPhase.PRE_WAKE
    assert run.wake_at == NEXT_WAKE + _DAY


@pytest.mark.parametrize(
    ("command", "state"),
    [
        (lambda alarm: alarm.snooze(timedelta(minutes=5), NOW), "upcoming"),
        (lambda alarm: alarm.dismiss(NOW), "upcoming"),
        (lambda alarm: alarm.expire(NOW), "not expired"),
    ],
)
def test_commands_outside_their_states_are_rejected(command, state: str) -> None:
    alarm = make_alarm()

    with pytest.raises(AlarmStateError):
        command(alarm)
    assert _state(alarm) is OccurrenceState.UPCOMING, state


def test_starting_a_stale_run_is_rejected() -> None:
    alarm = make_alarm(pre_wake_lead=None)

    with pytest.raises(AlarmStateError):
        alarm.start_run(
            DueRun(alarm.id, AlarmPhase.WAKE, NEXT_WAKE + _DAY, NEXT_WAKE + _DAY),
            NEXT_WAKE,
        )


def test_skip_next_skips_exactly_one_occurrence_and_is_cleaned_up_later() -> None:
    alarm = make_alarm(pre_wake_lead=None)

    alarm.skip_next()

    thursday = NEXT_WAKE + _DAY
    assert alarm.occurrence is not None
    assert alarm.occurrence.wake_at == thursday
    assert alarm.skipped_dates == {date(2026, 9, 16)}

    alarm.start_run(_due(alarm, thursday), thursday)
    alarm.dismiss(thursday + timedelta(minutes=2))

    assert alarm.occurrence is not None
    assert alarm.occurrence.wake_at == thursday + _DAY
    assert alarm.skipped_dates == frozenset()


def test_a_one_time_alarm_cannot_skip_and_finishes_once_dismissed() -> None:
    wake_at = NOW + timedelta(hours=8)
    alarm = make_alarm(recurrence=once_at(wake_at), pre_wake_lead=None)

    with pytest.raises(AlarmStateError):
        alarm.skip_next()

    alarm.start_run(_due(alarm, wake_at), wake_at)
    alarm.dismiss(wake_at + timedelta(minutes=1))

    assert alarm.occurrence is None
    assert alarm.is_finished


def test_a_missed_occurrence_expires_after_the_grace_period() -> None:
    alarm = make_alarm(pre_wake_lead=None)
    late = NEXT_WAKE + MISSED_GRACE + timedelta(minutes=1)

    alarm.expire(late)

    assert alarm.occurrence is not None
    assert alarm.occurrence.wake_at == NEXT_WAKE + _DAY


def test_disabling_clears_the_occurrence_and_enabling_recomputes_it() -> None:
    alarm = make_alarm()

    alarm.set_enabled(False, NOW)
    assert alarm.occurrence is None
    assert not alarm.is_finished

    alarm.set_enabled(True, NEXT_WAKE + timedelta(hours=1))
    assert alarm.occurrence is not None
    assert alarm.occurrence.wake_at == NEXT_WAKE + _DAY


def test_update_replaces_the_routine_and_resets_the_occurrence() -> None:
    alarm = make_alarm(pre_wake_lead=None)
    alarm.skip_next()
    wake_at = NOW + timedelta(hours=2)

    alarm.update(
        recurrence=once_at(wake_at),
        routine=AlarmRoutine("gentle-wake", note="ohne Musik"),
        now=NOW,
        pre_wake_lead=timedelta(minutes=10),
        name="Nap",
    )

    assert alarm.routine == AlarmRoutine("gentle-wake", note="ohne Musik")
    assert alarm.name == "Nap"
    assert alarm.skipped_dates == frozenset()
    assert alarm.occurrence is not None
    assert alarm.occurrence.wake_at == wake_at
    assert _state(alarm) is OccurrenceState.UPCOMING


@pytest.mark.parametrize(
    "create",
    [
        lambda: make_alarm(recurrence=once_at(NOW - timedelta(minutes=1))),
        lambda: make_alarm(pre_wake_lead=timedelta(0)),
        lambda: make_alarm(pre_wake_lead=timedelta(minutes=121)),
        lambda: make_alarm(owner_id=" "),
        lambda: AlarmRoutine(" "),
    ],
)
def test_invalid_alarms_are_rejected(create) -> None:
    with pytest.raises(InvalidAlarmError):
        create()


def test_snoozing_longer_than_the_maximum_is_rejected() -> None:
    alarm = make_alarm(pre_wake_lead=None)
    alarm.start_run(_due(alarm, NEXT_WAKE), NEXT_WAKE)

    with pytest.raises(InvalidAlarmError):
        alarm.snooze(timedelta(minutes=61), NEXT_WAKE)


def _due(alarm: Alarm, now) -> DueRun:
    run = alarm.next_due_run(now)
    assert run is not None
    return run


def _state(alarm: Alarm) -> OccurrenceState | None:
    return None if alarm.occurrence is None else alarm.occurrence.state
