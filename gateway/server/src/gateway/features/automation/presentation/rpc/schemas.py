from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal
from uuid import UUID
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, field_validator


class _AutomationSchema(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class AutomationRpcMethod(StrEnum):
    LIST = "automation.list"
    GET = "automation.get"
    CREATE = "automation.create"
    UPDATE = "automation.update"
    DELETE = "automation.delete"


class ScheduleKind(StrEnum):
    AT = "at"
    INTERVAL = "interval"
    CRON = "cron"


class AtSchedule(_AutomationSchema):
    kind: Literal[ScheduleKind.AT] = ScheduleKind.AT
    run_at: datetime


class IntervalSchedule(_AutomationSchema):
    kind: Literal[ScheduleKind.INTERVAL] = ScheduleKind.INTERVAL
    every_seconds: float = Field(gt=0)
    run_immediately: bool


class CronSchedule(_AutomationSchema):
    kind: Literal[ScheduleKind.CRON] = ScheduleKind.CRON
    expression: str
    timezone: str

    @field_validator("timezone")
    @classmethod
    def _resolvable_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (KeyError, ValueError) as error:
            raise ValueError(f"Unknown timezone: {value!r}") from error
        return value


type AutomationSchedule = Annotated[
    AtSchedule | IntervalSchedule | CronSchedule,
    Field(discriminator="kind"),
]


class SessionAutomationTargetResponse(_AutomationSchema):
    kind: Literal["session"]
    session_id: UUID


class ReminderAutomationPayload(_AutomationSchema):
    kind: Literal["reminder"]
    instruction: str
    created_from_turn_id: UUID


class AutomationResponse(_AutomationSchema):
    id: str
    name: str | None
    created_at: datetime
    next_run_at: datetime
    schedule: AutomationSchedule
    target: SessionAutomationTargetResponse
    payload: ReminderAutomationPayload


class ListAutomationsParams(_AutomationSchema):
    session_id: UUID


class ListAutomationsResponse(_AutomationSchema):
    automations: tuple[AutomationResponse, ...]


class GetAutomationParams(_AutomationSchema):
    session_id: UUID
    automation_id: str = Field(min_length=1)


class CreateAutomationParams(_AutomationSchema):
    session_id: UUID
    schedule: AutomationSchedule
    payload: ReminderAutomationPayload
    name: str | None = None


class UpdateAutomationParams(_AutomationSchema):
    session_id: UUID
    automation_id: str = Field(min_length=1)
    schedule: AutomationSchedule
    payload: ReminderAutomationPayload
    name: str | None = None


class DeleteAutomationParams(_AutomationSchema):
    session_id: UUID
    automation_id: str = Field(min_length=1)


class DeleteAutomationResponse(_AutomationSchema):
    deleted: str
