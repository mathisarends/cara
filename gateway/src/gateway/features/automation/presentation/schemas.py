from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal
from uuid import UUID
from zoneinfo import ZoneInfo

from pydantic import AwareDatetime, Field, field_validator

from gateway.features.automation.domain import ScheduleKind, TargetKind
from gateway.presentation.models import ApiModel


class PayloadKind(StrEnum):
    REMINDER = "reminder"


class AtSchedule(ApiModel):
    kind: Literal[ScheduleKind.AT]
    run_at: AwareDatetime


class IntervalSchedule(ApiModel):
    kind: Literal[ScheduleKind.INTERVAL]
    every_seconds: float = Field(gt=0)
    run_immediately: bool = False


class CronSchedule(ApiModel):
    kind: Literal[ScheduleKind.CRON]
    expression: str = Field(
        pattern=r"^\s*\S+(\s+\S+){4}\s*$",
        examples=["0 9 * * 1-5"],
    )
    timezone: str = Field(examples=["Europe/Berlin"])

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


class SessionTarget(ApiModel):
    kind: Literal[TargetKind.SESSION]
    session_id: UUID


class ChannelTarget(ApiModel):
    kind: Literal[TargetKind.CHANNEL]
    channel: str = Field(min_length=1, pattern=r"\S")


type AutomationTarget = Annotated[
    SessionTarget | ChannelTarget,
    Field(discriminator="kind"),
]


class ReminderPayload(ApiModel):
    kind: Literal[PayloadKind.REMINDER] = PayloadKind.REMINDER
    instruction: str = Field(min_length=1, pattern=r"\S")


class CreateAutomationRequest(ApiModel):
    target: AutomationTarget
    schedule: AutomationSchedule
    payload: ReminderPayload
    name: str | None = None


class UpdateAutomationRequest(ApiModel):
    schedule: AutomationSchedule
    payload: ReminderPayload
    name: str | None = None


class AutomationResponse(ApiModel):
    id: UUID
    owner_id: str
    name: str | None
    created_at: datetime
    next_run_at: datetime
    schedule: AutomationSchedule
    target: AutomationTarget
    payload: ReminderPayload


class AutomationListResponse(ApiModel):
    automations: tuple[AutomationResponse, ...]
