from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any
from uuid import UUID


@dataclass(frozen=True, slots=True)
class AgentChannelRef:
    name: str


@dataclass(frozen=True, slots=True)
class AgentSessionRef:
    id: UUID
    channel: AgentChannelRef


@dataclass(frozen=True, slots=True)
class AgentRunRequest:
    session: AgentSessionRef
    turn_id: UUID
    input_id: UUID | None
    input: str
    turn_metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class AgentUserMessage:
    id: UUID
    content: str


@dataclass(frozen=True, slots=True)
class AgentAssistantMessage:
    id: UUID
    content: str


class AgentToolCallState(StrEnum):
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class AgentToolCall:
    id: UUID
    call_id: str
    name: str
    arguments: dict[str, Any]
    state: AgentToolCallState
    result: Any = None
    error: str | None = None


@dataclass(frozen=True, slots=True)
class AgentToolCallSequence:
    id: UUID
    calls: tuple[AgentToolCall, ...]


type AgentContextEntry = (
    AgentUserMessage | AgentAssistantMessage | AgentToolCallSequence
)


@dataclass(frozen=True, slots=True)
class AgentContext:
    entries: tuple[AgentContextEntry, ...]
