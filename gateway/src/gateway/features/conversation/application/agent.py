from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID


@dataclass(frozen=True, slots=True)
class AgentChannelRef:
    name: str
    account_id: str | None = None


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


class AgentRuntime(ABC):
    @abstractmethod
    async def prepare(self, session: AgentSessionRef) -> None: ...

    @abstractmethod
    def run(self, request: AgentRunRequest) -> AsyncIterator[AgentEvent]: ...

    @abstractmethod
    async def steer(self, session: AgentSessionRef, text: str) -> None: ...

    @abstractmethod
    async def finish(self, session: AgentSessionRef) -> None: ...

    @abstractmethod
    async def close(self) -> None: ...
