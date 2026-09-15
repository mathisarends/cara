from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from typing import ClassVar, Literal
from zoneinfo import ZoneInfo


class ScheduleKind(StrEnum):
    AT = "at"
    INTERVAL = "interval"
    CRON = "cron"


@dataclass(frozen=True, slots=True)
class AtSchedule:
    kind: ClassVar[Literal[ScheduleKind.AT]] = ScheduleKind.AT
    run_at: datetime

    def __post_init__(self) -> None:
        if self.run_at.tzinfo is None or self.run_at.utcoffset() is None:
            raise ValueError("Scheduled time must include a timezone")


@dataclass(frozen=True, slots=True)
class IntervalSchedule:
    kind: ClassVar[Literal[ScheduleKind.INTERVAL]] = ScheduleKind.INTERVAL
    every: timedelta
    run_immediately: bool = False

    def __post_init__(self) -> None:
        if self.every <= timedelta(0):
            raise ValueError("Interval must be greater than zero")


@dataclass(frozen=True, slots=True)
class CronSchedule:
    kind: ClassVar[Literal[ScheduleKind.CRON]] = ScheduleKind.CRON
    expression: str
    timezone: str

    def __post_init__(self) -> None:
        if len(self.expression.split()) != 5:
            raise ValueError("Cron schedule must use a five-field expression")
        try:
            ZoneInfo(self.timezone)
        except (KeyError, ValueError) as error:
            raise ValueError(f"Unknown timezone: {self.timezone!r}") from error


type AutomationSchedule = AtSchedule | IntervalSchedule | CronSchedule
