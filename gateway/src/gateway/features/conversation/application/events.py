import uuid
from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from gateway.features.conversation.domain.values import ChannelRef


class ConversationEventType(StrEnum):
    TURN_STARTED = "turn.started"
    CHAT_DELTA = "chat.delta"
    CHAT_COMPLETED = "chat.completed"
    TURN_STEERED = "turn.steered"
    TOOL_CALL_STARTED = "tool_call.started"
    TOOL_CALL_COMPLETED = "tool_call.completed"
    TURN_FAILED = "turn.failed"
    TURN_COMPLETED = "turn.completed"
    TURN_CANCELLED = "turn.cancelled"


class ConversationEventBase(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True, extra="forbid", frozen=True)

    event_id: UUID = Field(default_factory=uuid.uuid4)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    session_id: UUID
    channel: ChannelRef
    sequence: int | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ConversationTurnStarted(ConversationEventBase):
    type: Literal[ConversationEventType.TURN_STARTED]


class ConversationChatDelta(ConversationEventBase):
    type: Literal[ConversationEventType.CHAT_DELTA]
    text: str


class ConversationChatCompleted(ConversationEventBase):
    type: Literal[ConversationEventType.CHAT_COMPLETED]
    text: str
    finish_reason: str


class ConversationTurnSteered(ConversationEventBase):
    type: Literal[ConversationEventType.TURN_STEERED]
    text: str


class ConversationToolCallStarted(ConversationEventBase):
    type: Literal[ConversationEventType.TOOL_CALL_STARTED]
    call_id: str
    name: str
    arguments: dict[str, Any]


class ConversationToolCallCompleted(ConversationEventBase):
    type: Literal[ConversationEventType.TOOL_CALL_COMPLETED]
    call_id: str
    name: str
    result: Any
    is_error: bool


class ConversationTurnFailed(ConversationEventBase):
    type: Literal[ConversationEventType.TURN_FAILED]
    code: str
    message: str


class ConversationTurnCompleted(ConversationEventBase):
    type: Literal[ConversationEventType.TURN_COMPLETED]


class ConversationTurnCancelled(ConversationEventBase):
    type: Literal[ConversationEventType.TURN_CANCELLED]


type ConversationEvent = Annotated[
    ConversationTurnStarted
    | ConversationChatDelta
    | ConversationChatCompleted
    | ConversationTurnSteered
    | ConversationToolCallStarted
    | ConversationToolCallCompleted
    | ConversationTurnFailed
    | ConversationTurnCompleted
    | ConversationTurnCancelled,
    Field(discriminator="type"),
]


CONVERSATION_EVENT_ADAPTER: TypeAdapter[ConversationEvent] = TypeAdapter(
    ConversationEvent
)


def create_conversation_event(
    event_type: ConversationEventType,
    session_id: UUID,
    channel: ChannelRef,
    data: dict[str, Any],
    *,
    event_id: UUID | None = None,
    timestamp: datetime | None = None,
    sequence: int | None = None,
    metadata: dict[str, Any] | None = None,
    call_id: str | None = None,
) -> ConversationEvent:
    event = {
        "type": event_type,
        "session_id": session_id,
        "channel": channel,
        "sequence": sequence,
        "metadata": metadata or {},
        **data,
    }
    if event_id is not None:
        event["event_id"] = event_id
    if timestamp is not None:
        event["timestamp"] = timestamp
    if call_id is not None:
        event["call_id"] = call_id
    return CONVERSATION_EVENT_ADAPTER.validate_python(event)
