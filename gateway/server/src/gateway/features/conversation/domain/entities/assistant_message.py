from datetime import datetime
from uuid import UUID

from gateway.shared import Entity


class AssistantMessage(Entity):
    def __init__(
        self,
        content: str,
        *,
        id: UUID | None = None,
        created_at: datetime | None = None,
    ) -> None:
        super().__init__(id=id, created_at=created_at)
        self._content = content

    @property
    def content(self) -> str:
        return self._content
