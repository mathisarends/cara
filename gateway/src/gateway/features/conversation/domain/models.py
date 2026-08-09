from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4


@dataclass(slots=True)
class Run:
    id: UUID
    session_id: UUID
    created_at: datetime
    status: str = "pending"


@dataclass(frozen=True, slots=True)
class GatewayEvent:
    type: str
    session_id: UUID | None
    data: dict[str, Any]
    event_id: UUID = field(default_factory=uuid4)
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    run_id: UUID | None = None
    call_id: str | None = None
    sequence: int | None = None
    request_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ChatDelta:
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ChatCompleted:
    text: str
    finish_reason: str = "stop"
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ToolCallStarted:
    call_id: str
    name: str
    arguments: dict[str, Any]
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ToolCallCompleted:
    call_id: str
    name: str
    result: Any
    is_error: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


type AgentOutput = ChatDelta | ChatCompleted | ToolCallStarted | ToolCallCompleted
