from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, tzinfo

from croniter import croniter


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


@dataclass(slots=True)
class ScheduledJob[PayloadT]:
    id: str
    trigger: Trigger
    payload: PayloadT
    next_run_at: datetime


@dataclass(frozen=True, slots=True)
class ScheduledRun[PayloadT]:
    job_id: str
    scheduled_for: datetime
    # None when this is the job's final run.
    next_run_at: datetime | None
    payload: PayloadT


type JobRunner[PayloadT] = Callable[[ScheduledRun[PayloadT]], Awaitable[None]]
