import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

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


@dataclass(frozen=True, slots=True)
class ConversationEvent:
    type: ConversationEventType
    session_id: UUID
    channel: ChannelRef
    data: dict[str, Any]
    event_id: UUID = field(default_factory=uuid.uuid4)
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    call_id: str | None = None
    sequence: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
