from datetime import datetime
from uuid import UUID

from sqlalchemy import Column, DateTime, Index, String, UniqueConstraint, text
from sqlmodel import Field, Relationship

from gateway.platform.database import DatabaseEntity


class VoiceSessionModel(DatabaseEntity, table=True):
    __tablename__ = "voice_sessions"
    __table_args__ = (
        Index("ix_voice_sessions_session_id", "session_id"),
        Index("ix_voice_sessions_device_id", "device_id"),
        Index(
            "uq_voice_sessions_open_device",
            "device_id",
            unique=True,
            sqlite_where=text("status = 'open'"),
        ),
    )

    session_id: UUID = Field(foreign_key="gateway_sessions.id", ondelete="CASCADE")
    room: str = Field(sa_column=Column("device_id", String, nullable=False))
    status: str
    input_encoding: str
    input_sample_rate: int
    input_channels: int
    output_encoding: str
    output_sample_rate: int
    output_channels: int
    last_sequence: int = 0
    closed_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))
    close_reason: str | None = None
    turns: list["VoiceTurnModel"] = Relationship(
        back_populates="voice_session",
        cascade_delete=True,
        sa_relationship_kwargs={"order_by": "VoiceTurnModel.index"},
    )


class VoiceTurnModel(DatabaseEntity, table=True):
    __tablename__ = "voice_turns"
    __table_args__ = (
        UniqueConstraint(
            "voice_session_id",
            "index",
            name="uq_voice_turns_session_index",
        ),
        Index("ix_voice_turns_user_message_id", "user_message_id"),
    )

    voice_session_id: UUID = Field(foreign_key="voice_sessions.id", ondelete="CASCADE")
    index: int
    activation: str
    status: str
    transcript: str | None = None
    user_message_id: UUID | None = Field(
        default=None,
        foreign_key="gateway_session_user_messages.id",
        ondelete="SET NULL",
    )
    stt_provider: str | None = None
    tts_provider: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    input_ended_at: datetime | None = Field(
        default=None, sa_type=DateTime(timezone=True)
    )
    transcribed_at: datetime | None = Field(
        default=None, sa_type=DateTime(timezone=True)
    )
    speech_started_at: datetime | None = Field(
        default=None, sa_type=DateTime(timezone=True)
    )
    ended_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))
    voice_session: VoiceSessionModel = Relationship(back_populates="turns")
