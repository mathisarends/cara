from datetime import datetime
from enum import StrEnum
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import Field

from gateway.presentation.models import ApiModel


class ItemType(StrEnum):
    USER_MESSAGE = "user_message"
    ASSISTANT_MESSAGE = "assistant_message"
    TOOL_CALL = "tool_call"


class ToolCallStatus(StrEnum):
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"


class SortOrder(StrEnum):
    ASC = "asc"
    DESC = "desc"


class SessionChannel(ApiModel):
    name: str = Field(min_length=1)


class CreateSessionRequest(ApiModel):
    channel: SessionChannel


class OpenSessionRequest(ApiModel):
    channel: SessionChannel


class SessionResponse(ApiModel):
    id: UUID
    created_at: datetime
    channel: SessionChannel


class SessionListResponse(ApiModel):
    sessions: tuple[SessionResponse, ...]


class ItemBase(ApiModel):
    id: UUID
    created_at: datetime


class UserMessageItem(ItemBase):
    type: Literal[ItemType.USER_MESSAGE]
    content: str


class AssistantMessageItem(ItemBase):
    type: Literal[ItemType.ASSISTANT_MESSAGE]
    content: str


class ToolCallItem(ItemBase):
    type: Literal[ItemType.TOOL_CALL]
    call_id: str
    name: str
    arguments: dict[str, Any]
    status: ToolCallStatus
    result: Any = None
    error: str | None = None


type Item = Annotated[
    UserMessageItem | AssistantMessageItem | ToolCallItem,
    Field(discriminator="type"),
]


class SessionSnapshotResponse(ApiModel):
    session: SessionResponse
    items: tuple[Item, ...]
    turn_active: bool
