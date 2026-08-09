from datetime import datetime
from enum import StrEnum
from typing import Annotated, Any, Literal
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from apscheduler.triggers.cron import CronTrigger
from pydantic import BaseModel, ConfigDict, Field, field_validator


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ScheduleKind(StrEnum):
    AT = "at"
    EVERY = "every"
    CRON = "cron"


class AtSchedule(_Model):
    kind: Literal[ScheduleKind.AT] = ScheduleKind.AT
    at: datetime

    @field_validator("at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("at must include a timezone")
        return value


class EverySchedule(_Model):
    kind: Literal[ScheduleKind.EVERY] = ScheduleKind.EVERY
    seconds: int = Field(gt=0)


class CronSchedule(_Model):
    kind: Literal[ScheduleKind.CRON] = ScheduleKind.CRON
    expression: str = Field(min_length=1)
    timezone: str = "UTC"

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as error:
            raise ValueError(f"unknown IANA timezone: {value}") from error
        return value

    @field_validator("expression")
    @classmethod
    def validate_expression(cls, value: str) -> str:
        try:
            CronTrigger.from_crontab(value)
        except ValueError as error:
            raise ValueError(f"invalid cron expression: {value}") from error
        return value


Schedule = Annotated[
    AtSchedule | EverySchedule | CronSchedule, Field(discriminator="kind")
]


class JobDefinition(_Model):
    id: UUID
    name: str = Field(min_length=1)
    schedule: Schedule
    payload: dict[str, Any]
    enabled: bool = True


class ScheduledJob(JobDefinition):
    next_run_at: datetime | None = None
