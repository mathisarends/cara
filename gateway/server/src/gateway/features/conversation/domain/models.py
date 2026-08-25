from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4


@dataclass(frozen=True, slots=True)
class ChannelRef:
    name: str
    account_id: str | None = None


class GatewayEventType(StrEnum):
    TURN_STARTED = "turn.started"
    CHAT_DELTA = "chat.delta"
    CHAT_COMPLETED = "chat.completed"
    TOOL_CALL_STARTED = "tool_call.started"
    TOOL_CALL_COMPLETED = "tool_call.completed"
    TURN_FAILED = "turn.failed"
    TURN_COMPLETED = "turn.completed"
    TURN_CANCELLED = "turn.cancelled"


@dataclass(frozen=True, slots=True)
class GatewayEvent:
    type: GatewayEventType
    session_id: UUID | None
    data: dict[str, Any]
    event_id: UUID = field(default_factory=uuid4)
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    call_id: str | None = None
    sequence: int | None = None
    request_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
