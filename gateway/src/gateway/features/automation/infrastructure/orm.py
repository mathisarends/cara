from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, Index
from sqlmodel import Field

from gateway.platform.database import DatabaseEntity


class AutomationModel(DatabaseEntity, table=True):
    __tablename__ = "gateway_automations"
    __table_args__ = (Index("ix_gateway_automations_owner_id", "owner_id"),)

    owner_id: str
    name: str | None = None
    target_kind: str
    target_session_id: UUID | None = None
    target_channel_name: str | None = None
    delivery_voice_room: str | None = None
    schedule_kind: str
    schedule_run_at: datetime | None = Field(
        default=None,
        sa_type=DateTime(timezone=True),
    )
    schedule_every_seconds: float | None = None
    schedule_run_immediately: bool | None = None
    schedule_cron_expression: str | None = None
    schedule_cron_timezone: str | None = None
    instruction: str
    next_run_at: datetime = Field(sa_type=DateTime(timezone=True))
