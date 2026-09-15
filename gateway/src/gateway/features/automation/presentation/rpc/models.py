from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal
from uuid import UUID
from zoneinfo import ZoneInfo

from pydantic import Field, field_validator
from pyrpckit import RpcModel

from gateway.features.automation.domain import ScheduleKind, TargetKind


class AutomationRpcMethod(StrEnum):
    LIST = "automation.list"
    GET = "automation.get"
    CREATE = "automation.create"
    UPDATE = "automation.update"
    DELETE = "automation.delete"


class PayloadKind(StrEnum):
    REMINDER = "reminder"


class AtSchedule(RpcModel):
    kind: Literal[ScheduleKind.AT] = ScheduleKind.AT
    run_at: datetime


class IntervalSchedule(RpcModel):
    kind: Literal[ScheduleKind.INTERVAL] = ScheduleKind.INTERVAL
    every_seconds: float = Field(gt=0)
    run_immediately: bool


class CronSchedule(RpcModel):
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


class SessionAutomationTarget(RpcModel):
    kind: Literal[TargetKind.SESSION] = TargetKind.SESSION
    session_id: UUID


type AutomationTarget = SessionAutomationTarget


class ReminderAutomationPayload(RpcModel):
    kind: Literal[PayloadKind.REMINDER] = PayloadKind.REMINDER
    instruction: str
    created_from_turn_id: UUID


class AutomationResponse(RpcModel):
    id: UUID
    owner_id: str
    name: str | None
    created_at: datetime
    next_run_at: datetime
    schedule: AutomationSchedule
    target: AutomationTarget
    payload: ReminderAutomationPayload


class ListAutomationsParams(RpcModel):
    owner_id: str = Field(min_length=1)


class ListAutomationsResponse(RpcModel):
    automations: tuple[AutomationResponse, ...]


class GetAutomationParams(RpcModel):
    owner_id: str = Field(min_length=1)
    automation_id: UUID


class CreateAutomationParams(RpcModel):
    owner_id: str = Field(min_length=1)
    target: AutomationTarget
    schedule: AutomationSchedule
    payload: ReminderAutomationPayload
    name: str | None = None


class UpdateAutomationParams(RpcModel):
    owner_id: str = Field(min_length=1)
    automation_id: UUID
    schedule: AutomationSchedule
    payload: ReminderAutomationPayload
    name: str | None = None


class DeleteAutomationParams(RpcModel):
    owner_id: str = Field(min_length=1)
    automation_id: UUID


class DeleteAutomationResponse(RpcModel):
    deleted: UUID
