from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass, field
from typing import Protocol


class ModelError(Exception):
    """Raised when a model violates the ChatModel contract."""


@dataclass(frozen=True, slots=True)
class ToolCall:
    id: str
    name: str
    arguments: str = "{}"


@dataclass(frozen=True, slots=True)
class SystemMessage:
    content: str


@dataclass(frozen=True, slots=True)
class UserMessage:
    content: str


@dataclass(frozen=True, slots=True)
class AssistantMessage:
    content: str
    tool_calls: tuple[ToolCall, ...] = ()
    provider_state: object | None = field(default=None, compare=False, repr=False)


@dataclass(frozen=True, slots=True)
class ToolResultMessage:
    tool_call_id: str
    tool_name: str
    content: str
    is_error: bool = False


type Message = SystemMessage | UserMessage | AssistantMessage | ToolResultMessage


@dataclass(frozen=True, slots=True)
class ModelTool:
    name: str
    description: str
    parameters: dict[str, object]


@dataclass(frozen=True, slots=True)
class TextDelta:
    delta: str


@dataclass(frozen=True, slots=True)
class ModelResponse:
    completion: str = ""
    finish_reason: str = "stop"
    tool_calls: tuple[ToolCall, ...] = ()
    provider_state: object | None = field(default=None, compare=False, repr=False)


type ModelEvent = TextDelta | ModelResponse


class ChatModel(Protocol):
    def stream(
        self,
        messages: Sequence[Message],
        *,
        tools: Sequence[ModelTool] = (),
    ) -> AsyncIterator[ModelEvent]: ...

    async def aclose(self) -> None: ...
