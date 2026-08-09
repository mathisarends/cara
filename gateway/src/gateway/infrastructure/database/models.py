from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import JSON, Column, DateTime, Index, UniqueConstraint
from sqlmodel import Field, Relationship, SQLModel


class DatabaseEntity(SQLModel):
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_type=DateTime(timezone=True),
    )


class SessionModel(DatabaseEntity, table=True):
    __tablename__ = "gateway_sessions"

    metadata_json: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column("metadata", JSON, nullable=False),
    )
    turn_active: bool = Field(default=False, nullable=False)
    user_messages: list["SessionUserMessageModel"] = Relationship(
        back_populates="session",
        cascade_delete=True,
        sa_relationship_kwargs={"order_by": "SessionUserMessageModel.position"},
    )
    assistant_messages: list["SessionAssistantMessageModel"] = Relationship(
        back_populates="session",
        cascade_delete=True,
        sa_relationship_kwargs={
            "order_by": "SessionAssistantMessageModel.position",
        },
    )
    tool_call_sequences: list["SessionToolCallSequenceModel"] = Relationship(
        back_populates="session",
        cascade_delete=True,
        sa_relationship_kwargs={
            "order_by": "SessionToolCallSequenceModel.position",
        },
    )


class SessionUserMessageModel(DatabaseEntity, table=True):
    __tablename__ = "gateway_session_user_messages"
    __table_args__ = (
        UniqueConstraint(
            "session_id",
            "position",
            name="uq_gateway_session_user_messages_session_position",
        ),
    )

    session_id: UUID = Field(
        foreign_key="gateway_sessions.id",
        ondelete="CASCADE",
    )
    position: int
    content: str

    session: SessionModel = Relationship(back_populates="user_messages")


class SessionAssistantMessageModel(DatabaseEntity, table=True):
    __tablename__ = "gateway_session_assistant_messages"
    __table_args__ = (
        UniqueConstraint(
            "session_id",
            "position",
            name="uq_gateway_session_assistant_messages_session_position",
        ),
    )

    session_id: UUID = Field(
        foreign_key="gateway_sessions.id",
        ondelete="CASCADE",
    )
    position: int
    content: str

    session: SessionModel = Relationship(back_populates="assistant_messages")


class SessionToolCallSequenceModel(DatabaseEntity, table=True):
    __tablename__ = "gateway_session_tool_call_sequences"
    __table_args__ = (
        UniqueConstraint(
            "session_id",
            "position",
            name="uq_gateway_session_tool_call_sequences_session_position",
        ),
    )

    session_id: UUID = Field(
        foreign_key="gateway_sessions.id",
        ondelete="CASCADE",
    )
    position: int

    session: SessionModel = Relationship(back_populates="tool_call_sequences")
    calls: list["SessionToolCallModel"] = Relationship(
        back_populates="sequence",
        cascade_delete=True,
        sa_relationship_kwargs={"order_by": "SessionToolCallModel.position"},
    )


class SessionToolCallModel(DatabaseEntity, table=True):
    __tablename__ = "gateway_session_tool_calls"
    __table_args__ = (
        UniqueConstraint(
            "sequence_id",
            "position",
            name="uq_gateway_session_tool_calls_sequence_position",
        ),
        UniqueConstraint(
            "sequence_id",
            "call_id",
            name="uq_gateway_session_tool_calls_sequence_call_id",
        ),
        Index("ix_gateway_session_tool_calls_call_id", "call_id"),
    )

    sequence_id: UUID = Field(
        foreign_key="gateway_session_tool_call_sequences.id",
        ondelete="CASCADE",
    )
    position: int
    call_id: str
    function_name: str
    function_arguments: dict[str, Any] = Field(
        sa_column=Column(JSON, nullable=False),
    )
    state: str
    result: Any = Field(default=None, sa_column=Column(JSON, nullable=True))
    error: str | None = None

    sequence: SessionToolCallSequenceModel = Relationship(back_populates="calls")


class ScheduledJobModel(DatabaseEntity, table=True):
    __tablename__ = "gateway_scheduled_jobs"

    name: str
    schedule: dict[str, Any] = Field(sa_column=Column(JSON, nullable=False))
    payload: dict[str, Any] = Field(sa_column=Column(JSON, nullable=False))
    enabled: bool = Field(default=True, nullable=False)
