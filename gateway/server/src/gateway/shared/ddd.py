import uuid
from datetime import UTC, datetime
from uuid import UUID


class Entity:
    def __init__(
        self,
        id: UUID | None = None,
        created_at: datetime | None = None,
    ) -> None:
        self._id = id if id is not None else uuid.uuid4()
        self._created_at = created_at if created_at is not None else datetime.now(UTC)

    @property
    def id(self) -> UUID:
        return self._id

    @property
    def created_at(self) -> datetime:
        return self._created_at


# Semantic sugar for marking aggregate roots in domain signatures.
Aggregate = Entity
