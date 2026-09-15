from datetime import date, timedelta

import pytest

from features.alarm.fakes import DAILY_AT_SIX, NEXT_WAKE, NOW, make_alarm, once_at
from gateway.features.alarm.domain import (
    Alarm,
    AlarmRecurrence,
    Occurrence,
    OccurrenceState,
)
from gateway.features.alarm.infrastructure.repository import SQLAlarmRepository


@pytest.mark.parametrize(
    "recurrence",
    [once_at(NOW + timedelta(hours=8)), DAILY_AT_SIX],
)
async def test_save_round_trips_every_field(
    alarm_repository: SQLAlarmRepository,
    recurrence: AlarmRecurrence,
) -> None:
    alarm = make_alarm(recurrence=recurrence, note="ohne Musik", name="Wecker")
    stored_alarm = Alarm(
        id=alarm.id,
        created_at=alarm.created_at,
        owner_id=alarm.owner_id,
        target=alarm.target,
        recurrence=alarm.recurrence,
        routine=alarm.routine,
        pre_wake_lead=alarm.pre_wake_lead,
        name=alarm.name,
        enabled=True,
        skipped_dates=frozenset({date(2026, 9, 17), date(2026, 9, 18)}),
        occurrence=Occurrence(
            wake_at=NEXT_WAKE,
            state=OccurrenceState.SNOOZED,
            snooze_count=2,
            snoozed_until=NEXT_WAKE + timedelta(minutes=18),
            activated_at=NEXT_WAKE + timedelta(minutes=9),
        ),
    )

    await alarm_repository.save(stored_alarm)
    stored = await alarm_repository.find_by_id(alarm.id)

    assert stored is not None
    assert _state(stored) == _state(stored_alarm)


async def test_a_disabled_alarm_round_trips_without_an_occurrence(
    alarm_repository: SQLAlarmRepository,
) -> None:
    alarm = make_alarm(pre_wake_lead=None)
    alarm.set_enabled(False, NOW)

    await alarm_repository.save(alarm)
    stored = await alarm_repository.find_by_id(alarm.id)

    assert stored is not None
    assert _state(stored) == _state(alarm)


async def test_find_by_owner_and_remove(
    alarm_repository: SQLAlarmRepository,
) -> None:
    mine = await alarm_repository.save(make_alarm())
    await alarm_repository.save(make_alarm(owner_id="someone-else"))

    found = await alarm_repository.find_by_owner("owner")
    await alarm_repository.remove(mine)

    assert [alarm.id for alarm in found] == [mine.id]
    assert await alarm_repository.find_by_owner("owner") == ()


def _state(alarm: Alarm) -> tuple[object, ...]:
    return (
        alarm.id,
        alarm.created_at,
        alarm.owner_id,
        alarm.target,
        alarm.recurrence,
        alarm.routine,
        alarm.pre_wake_lead,
        alarm.name,
        alarm.enabled,
        alarm.skipped_dates,
        alarm.occurrence,
    )
