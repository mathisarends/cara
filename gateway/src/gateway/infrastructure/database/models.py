from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel


class SessionEntity(SQLModel, table=True):
    __tablename__ = "gateway_sessions"

    id: UUID = Field(primary_key=True)
    created_at: datetime
    metadata_json: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column("metadata", JSON, nullable=False),
    )


class RunEntity(SQLModel, table=True):
    __tablename__ = "gateway_runs"

    id: UUID = Field(primary_key=True)
    session_id: UUID = Field(foreign_key="gateway_sessions.id", index=True)
    created_at: datetime
    status: str
