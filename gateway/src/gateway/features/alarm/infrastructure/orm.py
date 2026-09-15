from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, Index
from sqlmodel import Field

from gateway.platform.database import DatabaseEntity


class AlarmModel(DatabaseEntity, table=True):
    __tablename__ = "gateway_alarms"
    __table_args__ = (Index("ix_gateway_alarms_owner_id", "owner_id"),)

    owner_id: str
    name: str | None = None
    target_kind: str
    target_session_id: UUID | None = None
    recurrence_kind: str
    once_wake_at: datetime | None = Field(
        default=None,
        sa_type=DateTime(timezone=True),
    )
    weekly_days: str | None = None
    weekly_local_time: str | None = None
    weekly_timezone: str | None = None
    routine_skill: str
    routine_note: str | None = None
    pre_wake_lead_seconds: int | None = None
    enabled: bool
    skipped_dates: str
    occurrence_wake_at: datetime | None = Field(
        default=None,
        sa_type=DateTime(timezone=True),
    )
    occurrence_state: str | None = None
    occurrence_snooze_count: int | None = None
    occurrence_snoozed_until: datetime | None = Field(
        default=None,
        sa_type=DateTime(timezone=True),
    )
    occurrence_activated_at: datetime | None = Field(
        default=None,
        sa_type=DateTime(timezone=True),
    )
