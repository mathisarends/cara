from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Sequence
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field


class ModelError(Exception):
    """Raised when a model violates the ChatModel contract."""


class MessageType(StrEnum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL_RESULT = "tool_result"


class ModelEventType(StrEnum):
    TEXT_DELTA = "text_delta"
    RESPONSE = "response"


class ToolCall(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    name: str
    arguments: str = "{}"


class SystemMessage(BaseModel):
    model_config = ConfigDict(frozen=True)

    type: Literal[MessageType.SYSTEM] = MessageType.SYSTEM
    content: str


class UserMessage(BaseModel):
    model_config = ConfigDict(frozen=True)

    type: Literal[MessageType.USER] = MessageType.USER
    content: str


class AssistantMessage(BaseModel):
    model_config = ConfigDict(frozen=True)

    type: Literal[MessageType.ASSISTANT] = MessageType.ASSISTANT
    content: str
    tool_calls: tuple[ToolCall, ...] = ()
    provider_state: object | None = Field(default=None, repr=False)


class ToolResultMessage(BaseModel):
    model_config = ConfigDict(frozen=True)

    type: Literal[MessageType.TOOL_RESULT] = MessageType.TOOL_RESULT
    tool_call_id: str
    tool_name: str
    content: str
    is_error: bool = False


type Message = Annotated[
    SystemMessage | UserMessage | AssistantMessage | ToolResultMessage,
    Field(discriminator="type"),
]


class ModelTool(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    description: str
    parameters: dict[str, object]


class TextDelta(BaseModel):
    model_config = ConfigDict(frozen=True)

    type: Literal[ModelEventType.TEXT_DELTA] = ModelEventType.TEXT_DELTA
    delta: str


class ModelResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    type: Literal[ModelEventType.RESPONSE] = ModelEventType.RESPONSE
    completion: str = ""
    finish_reason: str = "stop"
    tool_calls: tuple[ToolCall, ...] = ()
    provider_state: object | None = Field(default=None, repr=False)


type ModelEvent = Annotated[TextDelta | ModelResponse, Field(discriminator="type")]


class ChatModel(ABC):
    @abstractmethod
    def stream(
        self,
        messages: Sequence[Message],
        *,
        tools: Sequence[ModelTool] = (),
    ) -> AsyncIterator[ModelEvent]: ...

    @abstractmethod
    async def aclose(self) -> None: ...
