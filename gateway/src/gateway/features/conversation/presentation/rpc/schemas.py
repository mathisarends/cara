from datetime import datetime
from enum import StrEnum
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import Field, TypeAdapter

from gateway.presentation.rpc import WireSchema


class ItemType(StrEnum):
    USER_MESSAGE = "user_message"
    ASSISTANT_MESSAGE = "assistant_message"
    TOOL_CALL = "tool_call"


class ToolCallStatus(StrEnum):
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"


class SessionChannel(WireSchema):
    name: str = Field(min_length=1)
    account_id: str | None = Field(default=None, min_length=1)


class SessionResponse(WireSchema):
    id: UUID
    created_at: datetime
    channel: SessionChannel
    metadata: dict[str, Any] = Field(default_factory=dict)


class ItemBase(WireSchema):
    id: UUID
    created_at: datetime


class UserMessageItem(ItemBase):
    type: Literal[ItemType.USER_MESSAGE] = ItemType.USER_MESSAGE
    content: str


class AssistantMessageItem(ItemBase):
    type: Literal[ItemType.ASSISTANT_MESSAGE] = ItemType.ASSISTANT_MESSAGE
    content: str


class ToolCallItem(ItemBase):
    type: Literal[ItemType.TOOL_CALL] = ItemType.TOOL_CALL
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


class ConversationRpcMethod(StrEnum):
    SESSION_CREATE = "session.create"
    SESSION_OPEN = "session.open"
    SESSION_GET = "session.get"
    SUBSCRIPTION_SUBSCRIBE = "subscription.subscribe"
    SUBSCRIPTION_UNSUBSCRIBE = "subscription.unsubscribe"
    TURN_PREPARE = "turn.prepare"
    TURN_START = "turn.start"
    TURN_STEER = "turn.steer"
    TURN_FINISH = "turn.finish"
    TURN_CANCEL = "turn.cancel"


class RpcNotificationMethod(StrEnum):
    SESSION_EVENT = "session.event"


class SessionParams(WireSchema):
    session_id: UUID


class CreateSessionParams(WireSchema):
    channel: SessionChannel
    metadata: dict[str, object] = Field(default_factory=dict)


class OpenSessionParams(CreateSessionParams):
    pass


class StartTurnParams(SessionParams):
    message: str = Field(min_length=1)
    metadata: dict[str, object] = Field(default_factory=dict)


class SteerTurnParams(SessionParams):
    message: str = Field(min_length=1)


class SubscriptionResult(WireSchema):
    subscribed: UUID


class UnsubscriptionResult(WireSchema):
    unsubscribed: UUID


class TurnCommandResult(WireSchema):
    session_id: UUID


class SessionEventType(StrEnum):
    TURN_STARTED = "turn.started"
    CHAT_DELTA = "chat.delta"
    CHAT_COMPLETED = "chat.completed"
    TURN_STEERED = "turn.steered"
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


class TurnStarted(EventBase):
    type: Literal[SessionEventType.TURN_STARTED] = SessionEventType.TURN_STARTED


class ChatDelta(EventBase):
    type: Literal[SessionEventType.CHAT_DELTA] = SessionEventType.CHAT_DELTA
    text: str


class ChatCompleted(EventBase):
    type: Literal[SessionEventType.CHAT_COMPLETED] = SessionEventType.CHAT_COMPLETED
    text: str
    finish_reason: str


class TurnSteered(EventBase):
    type: Literal[SessionEventType.TURN_STEERED] = SessionEventType.TURN_STEERED
    text: str


class ToolCallStarted(EventBase):
    type: Literal[SessionEventType.TOOL_CALL_STARTED] = (
        SessionEventType.TOOL_CALL_STARTED
    )
    call_id: str
    name: str
    arguments: dict[str, Any]


class ToolCallCompleted(EventBase):
    type: Literal[SessionEventType.TOOL_CALL_COMPLETED] = (
        SessionEventType.TOOL_CALL_COMPLETED
    )
    call_id: str
    name: str
    result: Any
    is_error: bool


class TurnCompleted(EventBase):
    type: Literal[SessionEventType.TURN_COMPLETED] = SessionEventType.TURN_COMPLETED


class TurnCancelled(EventBase):
    type: Literal[SessionEventType.TURN_CANCELLED] = SessionEventType.TURN_CANCELLED


class TurnFailed(EventBase):
    type: Literal[SessionEventType.TURN_FAILED] = SessionEventType.TURN_FAILED
    code: str
    message: str


type SessionEvent = Annotated[
    TurnStarted
    | ChatDelta
    | ChatCompleted
    | TurnSteered
    | ToolCallStarted
    | ToolCallCompleted
    | TurnCompleted
    | TurnCancelled
    | TurnFailed,
    Field(discriminator="type"),
]

SESSION_EVENT_ADAPTER: TypeAdapter[SessionEvent] = TypeAdapter(SessionEvent)
