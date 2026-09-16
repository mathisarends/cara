from datetime import datetime
from enum import StrEnum
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import Field, TypeAdapter

from gateway.presentation.models import ApiModel


class ConversationRpcMethod(StrEnum):
    SUBSCRIPTION_SUBSCRIBE = "subscription.subscribe"
    SUBSCRIPTION_UNSUBSCRIBE = "subscription.unsubscribe"
    SUBSCRIPTION_SUBSCRIBE_CHANNEL = "subscription.subscribe_channel"
    SUBSCRIPTION_UNSUBSCRIBE_CHANNEL = "subscription.unsubscribe_channel"
    TURN_PREPARE = "turn.prepare"
    TURN_START = "turn.start"
    TURN_STEER = "turn.steer"
    TURN_FINISH = "turn.finish"
    TURN_CANCEL = "turn.cancel"


class RpcNotificationMethod(StrEnum):
    SESSION_EVENT = "session.event"


class SessionParams(ApiModel):
    session_id: UUID


class ChannelParams(ApiModel):
    channel: str = Field(min_length=1)


class StartTurnParams(SessionParams):
    message: str = Field(min_length=1)


class SteerTurnParams(SessionParams):
    message: str = Field(min_length=1)


class SubscriptionResult(ApiModel):
    subscribed: UUID


class UnsubscriptionResult(ApiModel):
    unsubscribed: UUID


class ChannelSubscriptionResult(ApiModel):
    subscribed_channel: str


class ChannelUnsubscriptionResult(ApiModel):
    unsubscribed_channel: str


class TurnCommandResult(ApiModel):
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


class EventBase(ApiModel):
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
