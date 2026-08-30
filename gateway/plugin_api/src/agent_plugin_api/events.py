from dataclasses import dataclass, field
from typing import Any


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
class TurnSteered:
    text: str
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


type AgentEvent = (
    ChatDelta | ChatCompleted | TurnSteered | ToolCallStarted | ToolCallCompleted
)
