from dataclasses import dataclass
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo


@dataclass(frozen=True, slots=True)
class AtSchedule:
    run_at: datetime

    def __post_init__(self) -> None:
        if self.run_at.tzinfo is None or self.run_at.utcoffset() is None:
            raise ValueError("Scheduled time must include a timezone")


@dataclass(frozen=True, slots=True)
class IntervalSchedule:
    every: timedelta
    run_immediately: bool = False

    def __post_init__(self) -> None:
        if self.every <= timedelta(0):
            raise ValueError("Interval must be greater than zero")


@dataclass(frozen=True, slots=True)
class CronSchedule:
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
