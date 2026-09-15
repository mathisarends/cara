from datetime import date, datetime
from enum import StrEnum
from typing import Annotated, Literal
from uuid import UUID
from zoneinfo import ZoneInfo

from pydantic import Field, field_validator
from pyrpckit import RpcModel

from gateway.features.alarm.domain import (
    AlarmPhase,
    OccurrenceState,
    RecurrenceKind,
    Weekday,
)
from gateway.features.alarm.domain.target import TargetKind


class AlarmRpcMethod(StrEnum):
    LIST = "alarm.list"
    GET = "alarm.get"
    CREATE = "alarm.create"
    UPDATE = "alarm.update"
    DELETE = "alarm.delete"
    SET_ENABLED = "alarm.set_enabled"
    SKIP_NEXT = "alarm.skip_next"
    SNOOZE = "alarm.snooze"
    DISMISS = "alarm.dismiss"


class OnceAlarmRecurrence(RpcModel):
    kind: Literal[RecurrenceKind.ONCE] = RecurrenceKind.ONCE
    wake_at: datetime


class WeeklyAlarmRecurrence(RpcModel):
    kind: Literal[RecurrenceKind.WEEKLY] = RecurrenceKind.WEEKLY
    days: tuple[Weekday, ...] = Field(min_length=1)
    local_time: str = Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$", examples=["06:30"])
    timezone: str

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


class SessionAlarmTarget(RpcModel):
    kind: Literal[TargetKind.SESSION] = TargetKind.SESSION
    session_id: UUID


type AlarmTarget = SessionAlarmTarget


class AlarmRoutine(RpcModel):
    skill: str = Field(min_length=1)
    note: str | None = None


class AlarmOccurrence(RpcModel):
    wake_at: datetime
    state: OccurrenceState
    snooze_count: int
    snoozed_until: datetime | None


class AlarmNextRun(RpcModel):
    phase: AlarmPhase
    due_at: datetime


class AlarmResponse(RpcModel):
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


class ListAlarmsParams(RpcModel):
    owner_id: str = Field(min_length=1)


class ListAlarmsResponse(RpcModel):
    alarms: tuple[AlarmResponse, ...]


class GetAlarmParams(RpcModel):
    owner_id: str = Field(min_length=1)
    alarm_id: UUID


class CreateAlarmParams(RpcModel):
    owner_id: str = Field(min_length=1)
    target: AlarmTarget
    recurrence: AlarmRecurrence
    routine: AlarmRoutine
    pre_wake_minutes: int | None = Field(default=None, ge=1, le=120)
    name: str | None = None


class UpdateAlarmParams(RpcModel):
    owner_id: str = Field(min_length=1)
    alarm_id: UUID
    recurrence: AlarmRecurrence
    routine: AlarmRoutine
    pre_wake_minutes: int | None = Field(default=None, ge=1, le=120)
    name: str | None = None


class DeleteAlarmParams(RpcModel):
    owner_id: str = Field(min_length=1)
    alarm_id: UUID


class DeleteAlarmResponse(RpcModel):
    deleted: UUID


class SetAlarmEnabledParams(RpcModel):
    owner_id: str = Field(min_length=1)
    alarm_id: UUID
    enabled: bool


class SkipNextAlarmParams(RpcModel):
    owner_id: str = Field(min_length=1)
    alarm_id: UUID


class SnoozeAlarmParams(RpcModel):
    owner_id: str = Field(min_length=1)
    alarm_id: UUID
    minutes: int = Field(ge=1, le=60)


class DismissAlarmParams(RpcModel):
    owner_id: str = Field(min_length=1)
    alarm_id: UUID


class DismissAlarmResponse(RpcModel):
    # Null once a one-time alarm has been removed.
    alarm: AlarmResponse | None
