from datetime import date, datetime
from typing import Annotated, Literal
from uuid import UUID
from zoneinfo import ZoneInfo

from pydantic import AwareDatetime, Field, field_validator

from gateway.features.alarm.domain import (
    AlarmPhase,
    OccurrenceState,
    RecurrenceKind,
    Weekday,
)
from gateway.features.alarm.domain.target import TargetKind
from gateway.presentation.models import ApiModel


class OnceAlarmRecurrence(ApiModel):
    kind: Literal[RecurrenceKind.ONCE]
    wake_at: AwareDatetime


class WeeklyAlarmRecurrence(ApiModel):
    kind: Literal[RecurrenceKind.WEEKLY]
    days: tuple[Weekday, ...] = Field(min_length=1)
    local_time: str = Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$", examples=["06:30"])
    timezone: str = Field(examples=["Europe/Berlin"])

    @field_validator("timezone")
    @classmethod
    def _resolvable_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (KeyError, ValueError) as error:
            raise ValueError(f"Unknown timezone: {value!r}") from error
        return value


type AlarmRecurrence = Annotated[
    OnceAlarmRecurrence | WeeklyAlarmRecurrence,
    Field(discriminator="kind"),
]


class SessionAlarmTarget(ApiModel):
    kind: Literal[TargetKind.SESSION] = TargetKind.SESSION
    session_id: UUID


type AlarmTarget = SessionAlarmTarget


class AlarmRoutine(ApiModel):
    skill: str = Field(min_length=1, pattern=r"\S", examples=["wake-up"])
    note: str | None = None


class AlarmOccurrence(ApiModel):
    wake_at: datetime
    state: OccurrenceState
    snooze_count: int
    snoozed_until: datetime | None


class AlarmNextRun(ApiModel):
    phase: AlarmPhase
    due_at: datetime


class CreateAlarmRequest(ApiModel):
    target: AlarmTarget
    recurrence: AlarmRecurrence
    routine: AlarmRoutine
    pre_wake_minutes: int | None = Field(default=None, ge=1, le=120)
    name: str | None = None
    room: str | None = Field(default=None, min_length=1, pattern=r"\S")


class UpdateAlarmRequest(ApiModel):
    recurrence: AlarmRecurrence
    routine: AlarmRoutine
    pre_wake_minutes: int | None = Field(default=None, ge=1, le=120)
    name: str | None = None
    room: str | None = Field(default=None, min_length=1, pattern=r"\S")


class SetAlarmEnabledRequest(ApiModel):
    enabled: bool


class SnoozeAlarmRequest(ApiModel):
    minutes: int = Field(ge=1, le=60)


class AlarmResponse(ApiModel):
    id: UUID
    owner_id: str
    name: str | None
    created_at: datetime
    enabled: bool
    target: AlarmTarget
    recurrence: AlarmRecurrence
    routine: AlarmRoutine
    pre_wake_minutes: int | None
    skipped_dates: tuple[date, ...]
    occurrence: AlarmOccurrence | None
    next_run: AlarmNextRun | None
    room: str | None


class AlarmListResponse(ApiModel):
    alarms: tuple[AlarmResponse, ...]


class DismissAlarmResponse(ApiModel):
    alarm: AlarmResponse | None
