import uuid
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import DateTime
from sqlmodel import Field, SQLModel


class DatabaseEntity(SQLModel):
    id: UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_type=DateTime(timezone=True),
    )
