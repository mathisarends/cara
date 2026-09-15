from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from enum import StrEnum
from typing import ClassVar, Literal
from zoneinfo import ZoneInfo

from gateway.features.alarm.domain.errors import InvalidAlarmError


class Weekday(StrEnum):
    MON = "mon"
    TUE = "tue"
    WED = "wed"
    THU = "thu"
    FRI = "fri"
    SAT = "sat"
    SUN = "sun"


class RecurrenceKind(StrEnum):
    ONCE = "once"
    WEEKLY = "weekly"


@dataclass(frozen=True, slots=True)
class OnceRecurrence:
    kind: ClassVar[Literal[RecurrenceKind.ONCE]] = RecurrenceKind.ONCE
    wake_at: datetime

    def __post_init__(self) -> None:
        if self.wake_at.tzinfo is None or self.wake_at.utcoffset() is None:
            raise InvalidAlarmError("Wake time must include a timezone")


@dataclass(frozen=True, slots=True)
class WeeklyRecurrence:
    kind: ClassVar[Literal[RecurrenceKind.WEEKLY]] = RecurrenceKind.WEEKLY
    days: frozenset[Weekday]
    local_time: time
    timezone: str

    def __post_init__(self) -> None:
        if not self.days:
            raise InvalidAlarmError("A weekly alarm needs at least one weekday")
        if self.local_time.tzinfo is not None:
            raise InvalidAlarmError("Weekly wake time must be a local wall-clock time")
        if self.local_time.second or self.local_time.microsecond:
            raise InvalidAlarmError("Weekly wake time must be a whole minute")
        try:
            ZoneInfo(self.timezone)
        except (KeyError, ValueError) as error:
            raise InvalidAlarmError(f"Unknown timezone: {self.timezone!r}") from error

    def local_date(self, instant: datetime) -> date:
        return instant.astimezone(ZoneInfo(self.timezone)).date()

    def next_wake_at(self, after: datetime, skipped_dates: frozenset[date]) -> datetime:
        zone = ZoneInfo(self.timezone)
        day = after.astimezone(zone).date()
        while True:
            if _WEEKDAYS[day.weekday()] in self.days and day not in skipped_dates:
                # fold=0 resolves a wall-clock time inside a DST gap past the gap
                # (02:30 -> 03:30) and a repeated one to its first occurrence.
                local = datetime.combine(day, self.local_time, tzinfo=zone)
                wake_at = local.astimezone(UTC)
                if wake_at > after:
                    return wake_at
            day += timedelta(days=1)


type AlarmRecurrence = OnceRecurrence | WeeklyRecurrence

_WEEKDAYS = tuple(Weekday)
