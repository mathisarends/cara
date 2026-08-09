"""Typed mirror of the Cara Gateway OpenAPI schema in ``openapi.json``.

Regenerate this module from the served spec when the gateway API changes; no
hand-written client logic belongs here.
"""

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, TypeAdapter


class GatewayEventType(StrEnum):
    CHAT_DELTA = "chat.delta"
    CHAT_COMPLETED = "chat.completed"
    TOOL_CALL_STARTED = "tool_call.started"
    TOOL_CALL_COMPLETED = "tool_call.completed"


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"


class ReadinessResponse(BaseModel):
    status: Literal["ready"] = "ready"


class SessionCreateRequest(BaseModel):
    metadata: dict[str, Any] = Field(default_factory=dict)


class SessionResponse(BaseModel):
    id: UUID
    created_at: datetime
    metadata: dict[str, Any]


class ChatRequest(BaseModel):
    text: str = Field(min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ErrorResponse(BaseModel):
    detail: str


class ValidationError(BaseModel):
    loc: list[str | int]
    msg: str
    type: str
    input: Any = None
    ctx: dict[str, Any] | None = None


class HTTPValidationError(BaseModel):
    detail: list[ValidationError] = Field(default_factory=list)


class ChatDeltaPayload(BaseModel):
    text: str


class ChatCompletedPayload(BaseModel):
    text: str
    finish_reason: str


class ToolCallStartedPayload(BaseModel):
    name: str
    arguments: dict[str, Any]


class ToolCallCompletedPayload(BaseModel):
    name: str
    result: Any
    is_error: bool


class EventEnvelope[PayloadT: BaseModel](BaseModel):
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


type GatewayEventMessage = Annotated[
    ChatDeltaEvent | ChatCompletedEvent | ToolCallStartedEvent | ToolCallCompletedEvent,
    Field(discriminator="type"),
]

event_adapter: TypeAdapter[GatewayEventMessage] = TypeAdapter(GatewayEventMessage)
