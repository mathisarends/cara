from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, tzinfo
from typing import Literal

from croniter import croniter

type ScheduleKind = Literal["at", "interval", "cron"]


@dataclass(frozen=True, slots=True)
class At:
    when: datetime

    def __post_init__(self) -> None:
        if self.when.tzinfo is None or self.when.utcoffset() is None:
            raise ValueError("Scheduled time must include a timezone")


@dataclass(frozen=True, slots=True)
class Interval:
    every: timedelta
    run_immediately: bool = True

    def __post_init__(self) -> None:
        if self.every <= timedelta(0):
            raise ValueError("Interval must be greater than zero")


@dataclass(frozen=True, slots=True)
class Cron:
    expression: str
    timezone: tzinfo

    def __post_init__(self) -> None:
        if len(self.expression.split()) != 5 or not croniter.is_valid(self.expression):
            raise ValueError(f"Invalid five-field cron expression: {self.expression!r}")


type Trigger = At | Interval | Cron


@dataclass(frozen=True, slots=True)
class ScheduledJob[PayloadT]:
    id: str
    trigger: Trigger
    payload: PayloadT
    created_at: datetime
    next_run_at: datetime
    name: str | None = None

    def __post_init__(self) -> None:
        if not self.id.strip():
            raise ValueError("Job id must not be empty")
        if self.created_at.tzinfo is None or self.created_at.utcoffset() is None:
            raise ValueError("Job creation time must include a timezone")
        if self.next_run_at.tzinfo is None or self.next_run_at.utcoffset() is None:
            raise ValueError("Next run time must include a timezone")

    @property
    def kind(self) -> ScheduleKind:
        match self.trigger:
            case At():
                return "at"
            case Interval():
                return "interval"
            case Cron():
                return "cron"


@dataclass(frozen=True, slots=True)
class ScheduledRun[PayloadT]:
    job_id: str
    kind: ScheduleKind
    scheduled_for: datetime
    payload: PayloadT
    job_name: str | None = None


type ErrorHandler[PayloadT] = Callable[
    [ScheduledJob[PayloadT], Exception], Awaitable[None]
]
