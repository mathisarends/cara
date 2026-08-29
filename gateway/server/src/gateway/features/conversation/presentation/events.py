from datetime import datetime
from enum import StrEnum
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import Field, TypeAdapter
from pyrpckit import event

from gateway.features.conversation.presentation.schemas import WireSchema


class SessionEventType(StrEnum):
    TURN_STARTED = "turn.started"
    CHAT_DELTA = "chat.delta"
    CHAT_COMPLETED = "chat.completed"
    TOOL_CALL_STARTED = "tool_call.started"
    TOOL_CALL_COMPLETED = "tool_call.completed"
    TURN_COMPLETED = "turn.completed"
    TURN_CANCELLED = "turn.cancelled"
    TURN_FAILED = "turn.failed"


class EventBase(WireSchema):
    event_id: UUID
    timestamp: datetime
    session_id: UUID
    sequence: int
    metadata: dict[str, Any] = Field(default_factory=dict)


@event
class TurnStarted(EventBase):
    type: Literal[SessionEventType.TURN_STARTED] = SessionEventType.TURN_STARTED


@event
class ChatDelta(EventBase):
    type: Literal[SessionEventType.CHAT_DELTA] = SessionEventType.CHAT_DELTA
    text: str


@event
class ChatCompleted(EventBase):
    type: Literal[SessionEventType.CHAT_COMPLETED] = SessionEventType.CHAT_COMPLETED
    text: str
    finish_reason: str


@event
class ToolCallStarted(EventBase):
    type: Literal[SessionEventType.TOOL_CALL_STARTED] = (
        SessionEventType.TOOL_CALL_STARTED
    )
    call_id: str
    name: str
    arguments: dict[str, Any]


@event
class ToolCallCompleted(EventBase):
    type: Literal[SessionEventType.TOOL_CALL_COMPLETED] = (
        SessionEventType.TOOL_CALL_COMPLETED
    )
    call_id: str
    name: str
    result: Any
    is_error: bool


@event
class TurnCompleted(EventBase):
    type: Literal[SessionEventType.TURN_COMPLETED] = SessionEventType.TURN_COMPLETED


@event
class TurnCancelled(EventBase):
    type: Literal[SessionEventType.TURN_CANCELLED] = SessionEventType.TURN_CANCELLED


@event
class TurnFailed(EventBase):
    type: Literal[SessionEventType.TURN_FAILED] = SessionEventType.TURN_FAILED
    code: str
    message: str


type SessionEvent = Annotated[
    TurnStarted
    | ChatDelta
    | ChatCompleted
    | ToolCallStarted
    | ToolCallCompleted
    | TurnCompleted
    | TurnCancelled
    | TurnFailed,
    Field(discriminator="type"),
]

SESSION_EVENT_ADAPTER: TypeAdapter[SessionEvent] = TypeAdapter(SessionEvent)
