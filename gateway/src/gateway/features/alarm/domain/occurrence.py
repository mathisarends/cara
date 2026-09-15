from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID


class OccurrenceState(StrEnum):
    UPCOMING = "upcoming"
    PRE_WAKE = "pre_wake"
    ACTIVE = "active"
    SNOOZED = "snoozed"


@dataclass(frozen=True, slots=True)
class Occurrence:
    wake_at: datetime
    state: OccurrenceState
    snooze_count: int = 0
    snoozed_until: datetime | None = None
    activated_at: datetime | None = None


class AlarmPhase(StrEnum):
    PRE_WAKE = "pre_wake"
    WAKE = "wake"
    SNOOZE_END = "snooze_end"


@dataclass(frozen=True, slots=True)
class DueRun:
    alarm_id: UUID
    phase: AlarmPhase
    due_at: datetime
    # The occurrence this run belongs to.
    wake_at: datetime
