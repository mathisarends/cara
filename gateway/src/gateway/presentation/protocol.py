from datetime import datetime
from enum import StrEnum
from typing import Annotated, Any, Literal, Self

from pydantic import BaseModel, Field, TypeAdapter

from gateway.application import GatewayEvent, Session


class CommandType(StrEnum):
    SESSION_CREATE = "session.create"
    SESSION_GET = "session.get"
    CHAT_SEND = "chat.send"
    RUN_CANCEL = "run.cancel"


class SessionCreatePayload(BaseModel):
    metadata: dict[str, Any] = Field(default_factory=dict)


class SessionCreateCommand(BaseModel):
    type: Literal[CommandType.SESSION_CREATE]
    request_id: str
    payload: SessionCreatePayload = Field(default_factory=SessionCreatePayload)


class SessionGetCommand(BaseModel):
    type: Literal[CommandType.SESSION_GET]
    request_id: str
    session_id: str


class ChatSendPayload(BaseModel):
    text: str = Field(min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ChatSendCommand(BaseModel):
    type: Literal[CommandType.CHAT_SEND]
    request_id: str
    session_id: str
    payload: ChatSendPayload


class RunCancelPayload(BaseModel):
    run_id: str


class RunCancelCommand(BaseModel):
    type: Literal[CommandType.RUN_CANCEL]
    request_id: str
    session_id: str
    payload: RunCancelPayload


Command = Annotated[
    SessionCreateCommand | SessionGetCommand | ChatSendCommand | RunCancelCommand,
    Field(discriminator="type"),
]
command_adapter: TypeAdapter[Command] = TypeAdapter(Command)


class EventEnvelope(BaseModel):
    type: str
    event_id: str
    timestamp: datetime
    session_id: str | None = None
    run_id: str | None = None
    call_id: str | None = None
    sequence: int | None = None
    request_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    data: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def from_event(cls, event: GatewayEvent) -> Self:
        return cls(
            type=event.type,
            event_id=event.event_id,
            timestamp=event.timestamp,
            session_id=event.session_id,
            run_id=event.run_id,
            call_id=event.call_id,
            sequence=event.sequence,
            request_id=event.request_id,
            metadata=event.metadata,
            data=event.data,
        )


class SessionCreateRequest(BaseModel):
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Client-defined session metadata used for routing context.",
        examples=[{"channel": "terminal"}],
    )


class SessionResponse(BaseModel):
    id: str = Field(description="Stable session identifier.", examples=["sess_abc123"])
    created_at: datetime = Field(
        description="UTC timestamp when the session was created."
    )
    metadata: dict[str, Any] = Field(description="Client-defined session metadata.")

    @classmethod
    def from_session(cls, session: Session) -> Self:
        return cls(
            id=session.id,
            created_at=session.created_at,
            metadata=session.metadata,
        )


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"


class ReadinessResponse(BaseModel):
    status: Literal["ready"] = "ready"


class ErrorResponse(BaseModel):
    detail: str = Field(description="Human-readable error description.")
