from datetime import datetime
from enum import StrEnum
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import Field, TypeAdapter

from gateway.presentation.rpc import WireSchema


class ConversationRpcMethod(StrEnum):
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
