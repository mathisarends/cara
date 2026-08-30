from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class TextDelta:
    text: str


@dataclass(frozen=True, slots=True)
class TurnCompleted:
    text: str
    finish_reason: str = "stop"


@dataclass(frozen=True, slots=True)
class SteeringApplied:
    text: str


@dataclass(frozen=True, slots=True)
class ToolStarted:
    name: str
    call_id: str
    arguments: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ToolCompleted:
    name: str
    call_id: str
    result: Any = None
    is_error: bool = False


type AgentEvent = (
    TextDelta | TurnCompleted | SteeringApplied | ToolStarted | ToolCompleted
)
