from datetime import UTC, date, datetime, time
from zoneinfo import ZoneInfo

import pytest

from gateway.features.alarm.domain import (
    InvalidAlarmError,
    OnceRecurrence,
    Weekday,
    WeeklyRecurrence,
)

_BERLIN = ZoneInfo("Europe/Berlin")
_WORKDAYS = frozenset({Weekday.MON, Weekday.TUE, Weekday.WED, Weekday.THU, Weekday.FRI})


def test_the_next_workday_occurrence_skips_the_weekend() -> None:
    recurrence = WeeklyRecurrence(_WORKDAYS, time(5, 0), "Europe/Berlin")
    friday_morning = datetime(2026, 9, 18, 6, 0, tzinfo=_BERLIN)

    wake_at = recurrence.next_wake_at(friday_morning, frozenset())

    assert wake_at == datetime(2026, 9, 21, 5, 0, tzinfo=_BERLIN)
    assert wake_at.tzinfo is UTC


def test_the_next_occurrence_crosses_a_month_boundary() -> None:
    recurrence = WeeklyRecurrence(frozenset({Weekday.THU}), time(7, 0), "Europe/Berlin")

    wake_at = recurrence.next_wake_at(
        datetime(2026, 9, 24, 8, 0, tzinfo=_BERLIN), frozenset()
    )

    assert wake_at == datetime(2026, 10, 1, 7, 0, tzinfo=_BERLIN)


def test_a_wake_time_inside_the_spring_forward_gap_moves_past_the_gap() -> None:
    recurrence = WeeklyRecurrence(
        frozenset({Weekday.SUN}), time(2, 30), "Europe/Berlin"
    )

    wake_at = recurrence.next_wake_at(
        datetime(2027, 3, 27, 12, 0, tzinfo=UTC), frozenset()
    )

    assert wake_at == datetime(2027, 3, 28, 1, 30, tzinfo=UTC)
    assert wake_at.astimezone(_BERLIN).time() == time(3, 30)


def test_a_repeated_fall_back_wake_time_uses_its_first_occurrence() -> None:
    recurrence = WeeklyRecurrence(
        frozenset({Weekday.SUN}), time(2, 30), "Europe/Berlin"
    )

    wake_at = recurrence.next_wake_at(
        datetime(2026, 10, 24, 12, 0, tzinfo=UTC), frozenset()
    )

    assert wake_at == datetime(2026, 10, 25, 0, 30, tzinfo=UTC)


def test_skipped_dates_are_passed_over() -> None:
    recurrence = WeeklyRecurrence(frozenset(Weekday), time(6, 0), "Europe/Berlin")

    wake_at = recurrence.next_wake_at(
        datetime(2026, 9, 15, 20, 0, tzinfo=UTC),
        frozenset({date(2026, 9, 16)}),
    )

    assert wake_at == datetime(2026, 9, 17, 6, 0, tzinfo=_BERLIN)


@pytest.mark.parametrize(
    "arguments",
    [
        (frozenset(), time(6, 0), "Europe/Berlin"),
        (_WORKDAYS, time(6, 0), "Mars/Olympus_Mons"),
        (_WORKDAYS, time(6, 0, 30), "Europe/Berlin"),
        (_WORKDAYS, time(6, 0, tzinfo=UTC), "Europe/Berlin"),
    ],
)
def test_invalid_weekly_recurrences_are_rejected(
    arguments: tuple[frozenset[Weekday], time, str],
) -> None:
    with pytest.raises(InvalidAlarmError):
        WeeklyRecurrence(*arguments)


def test_a_one_time_wake_time_needs_a_timezone() -> None:
    with pytest.raises(InvalidAlarmError):
        OnceRecurrence(datetime(2026, 9, 16, 6, 0))
