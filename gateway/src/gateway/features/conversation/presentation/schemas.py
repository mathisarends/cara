from datetime import datetime
from enum import StrEnum
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import Field

from gateway.presentation.rpc import WireSchema


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


class SessionChannel(WireSchema):
    name: str = Field(min_length=1)


class CreateSessionRequest(WireSchema):
    channel: SessionChannel
    inactivity_timeout_seconds: float | None = Field(default=None, gt=0)


class OpenSessionRequest(WireSchema):
    channel: SessionChannel
    inactivity_timeout_seconds: float | None = Field(default=None, gt=0)


class SessionResponse(WireSchema):
    id: UUID
    created_at: datetime
    channel: SessionChannel


class SessionListResponse(WireSchema):
    sessions: tuple[SessionResponse, ...]


class ItemBase(WireSchema):
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


class SessionSnapshotResponse(WireSchema):
    session: SessionResponse
    items: tuple[Item, ...]
    turn_active: bool
