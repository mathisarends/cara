from datetime import datetime
from typing import Annotated, Any, Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from gateway.features.conversation.domain import (
    GatewayEvent,
    GatewayEventType,
    Session,
)


class ChatRequest(BaseModel):
    text: str = Field(min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)


class SessionResponse(BaseModel):
    id: UUID = Field(description="Stable session identifier.")
    created_at: datetime = Field(
        description="UTC timestamp when the session was created."
    )
    metadata: dict[str, Any] = Field(description="Client-defined session metadata.")

    @classmethod
    def from_domain(cls, session: Session) -> Self:
        return cls(
            id=session.id,
            created_at=session.created_at,
            metadata=session.metadata,
        )


class EventPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ChatDeltaPayload(EventPayload):
    text: str


class ChatCompletedPayload(EventPayload):
    text: str
    finish_reason: str


class ToolCallStartedPayload(EventPayload):
    name: str
    arguments: dict[str, Any]


class ToolCallCompletedPayload(EventPayload):
    name: str
    result: Any
    is_error: bool


class TurnFailedPayload(EventPayload):
    code: str
    message: str


class EventEnvelope[PayloadT: EventPayload](BaseModel):
    type: GatewayEventType
    event_id: UUID
    timestamp: datetime
    session_id: UUID
    call_id: str | None = None
    sequence: int
    metadata: dict[str, Any] = Field(default_factory=dict)
    data: PayloadT


class ChatDeltaEvent(EventEnvelope[ChatDeltaPayload]):
    type: Literal[GatewayEventType.CHAT_DELTA]


class ChatCompletedEvent(EventEnvelope[ChatCompletedPayload]):
    type: Literal[GatewayEventType.CHAT_COMPLETED]


class ToolCallStartedEvent(EventEnvelope[ToolCallStartedPayload]):
    type: Literal[GatewayEventType.TOOL_CALL_STARTED]


class ToolCallCompletedEvent(EventEnvelope[ToolCallCompletedPayload]):
    type: Literal[GatewayEventType.TOOL_CALL_COMPLETED]


class TurnFailedEvent(EventEnvelope[TurnFailedPayload]):
    type: Literal[GatewayEventType.TURN_FAILED]


type EventMessage = Annotated[
    ChatDeltaEvent
    | ChatCompletedEvent
    | ToolCallStartedEvent
    | ToolCallCompletedEvent
    | TurnFailedEvent,
    Field(discriminator="type"),
]
event_adapter: TypeAdapter[EventMessage] = TypeAdapter(EventMessage)


def event_message(event: GatewayEvent) -> EventMessage:
    return event_adapter.validate_python(
        {
            "type": event.type,
            "event_id": event.event_id,
            "timestamp": event.timestamp,
            "session_id": event.session_id,
            "call_id": event.call_id,
            "sequence": event.sequence,
            "metadata": event.metadata,
            "data": event.data,
        }
    )


class SessionCreateRequest(BaseModel):
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Client-defined session metadata used for routing context.",
        examples=[{"channel": "terminal"}],
    )


class ErrorResponse(BaseModel):
    detail: str = Field(description="Human-readable error description.")
