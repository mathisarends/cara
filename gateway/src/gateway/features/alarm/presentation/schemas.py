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
from gateway.presentation.rpc import WireSchema


class OnceAlarmRecurrence(WireSchema):
    kind: Literal[RecurrenceKind.ONCE] = RecurrenceKind.ONCE
    wake_at: AwareDatetime


class WeeklyAlarmRecurrence(WireSchema):
    kind: Literal[RecurrenceKind.WEEKLY] = RecurrenceKind.WEEKLY
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


class SessionAlarmTarget(WireSchema):
    kind: Literal[TargetKind.SESSION] = TargetKind.SESSION
    session_id: UUID


type AlarmTarget = SessionAlarmTarget


class AlarmRoutine(WireSchema):
    skill: str = Field(min_length=1, pattern=r"\S", examples=["wake-up"])
    note: str | None = None


class AlarmOccurrence(WireSchema):
    wake_at: datetime
    state: OccurrenceState
    snooze_count: int
    snoozed_until: datetime | None


class AlarmNextRun(WireSchema):
    phase: AlarmPhase
    due_at: datetime


class CreateAlarmRequest(WireSchema):
    target: AlarmTarget
    recurrence: AlarmRecurrence
    routine: AlarmRoutine
    pre_wake_minutes: int | None = Field(default=None, ge=1, le=120)
    name: str | None = None


class UpdateAlarmRequest(WireSchema):
    recurrence: AlarmRecurrence
    routine: AlarmRoutine
    pre_wake_minutes: int | None = Field(default=None, ge=1, le=120)
    name: str | None = None


class SetAlarmEnabledRequest(WireSchema):
    enabled: bool


class SnoozeAlarmRequest(WireSchema):
    minutes: int = Field(ge=1, le=60)


class AlarmResponse(WireSchema):
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


class AlarmListResponse(WireSchema):
    alarms: tuple[AlarmResponse, ...]


class DismissAlarmResponse(WireSchema):
    alarm: AlarmResponse | None
