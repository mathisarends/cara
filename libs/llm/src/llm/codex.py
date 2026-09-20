from collections.abc import AsyncIterator, Sequence
from enum import StrEnum

from pydantic_ai.messages import (
    ModelMessage as PydanticMessage,
)
from pydantic_ai.messages import (
    ModelRequest,
    PartDeltaEvent,
    PartStartEvent,
    TextPart,
    TextPartDelta,
    ToolCallPart,
    ToolReturnPart,
)
from pydantic_ai.messages import (
    ModelResponse as PydanticResponse,
)
from pydantic_ai.models import ModelRequestParameters
from pydantic_ai.models.openai import OpenAIResponsesModelSettings
from pydantic_ai.models.openai_codex import OpenAICodexModel
from pydantic_ai.providers.openai_codex import OpenAICodexProvider
from pydantic_ai.tools import ToolDefinition
from pydantic_ai.usage import RequestUsage

from llm.ports import (
    AssistantMessage,
    ChatModel,
    Message,
    ModelEvent,
    ModelResponse,
    ModelTool,
    SystemMessage,
    TextDelta,
    ToolCall,
    ToolResultMessage,
    Usage,
    UserMessage,
)


class CodexModel(StrEnum):
    LUNA = "gpt-5.6-luna"
    TERRA = "gpt-5.6-terra"
    SOL = "gpt-5.6-sol"


class CodexReasoningEffort(StrEnum):
    NONE = "none"
    MINIMAL = "minimal"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    XHIGH = "xhigh"
    MAX = "max"


class PydanticAICodexModel(ChatModel):
    """HTTP adapter for Codex subscription authentication."""

    def __init__(
        self,
        model: CodexModel,
        *,
        reasoning_effort: CodexReasoningEffort | None = None,
    ) -> None:
        self._provider = OpenAICodexProvider()
        self._model = OpenAICodexModel(model.value, provider=self._provider)
        self._settings = (
            OpenAIResponsesModelSettings(openai_reasoning_effort=reasoning_effort.value)
            if reasoning_effort is not None
            else None
        )

    async def stream(
        self,
        messages: Sequence[Message],
        *,
        tools: Sequence[ModelTool] = (),
    ) -> AsyncIterator[ModelEvent]:
        async with self._model.request_stream(
            _pydantic_messages(messages),
            self._settings,
            _request_parameters(tools),
        ) as response:
            async for event in response:
                delta = _text_delta(event)
                if delta:
                    yield TextDelta(delta=delta)
            final = response.get()

        yield _model_response(final)

    async def invoke(
        self,
        messages: Sequence[Message],
        *,
        tools: Sequence[ModelTool] = (),
    ) -> ModelResponse:
        response = await self._model.request(
            _pydantic_messages(messages),
            self._settings,
            _request_parameters(tools),
        )
        return _model_response(response)

    async def aclose(self) -> None:
        await self._provider.client.close()


def create_codex_model(
    model: CodexModel,
    *,
    reasoning_effort: CodexReasoningEffort | None = None,
) -> PydanticAICodexModel:
    return PydanticAICodexModel(model, reasoning_effort=reasoning_effort)


def _request_parameters(tools: Sequence[ModelTool]) -> ModelRequestParameters:
    return ModelRequestParameters(
        function_tools=[_tool_definition(tool) for tool in tools]
    )


def _model_response(response: PydanticResponse) -> ModelResponse:
    return ModelResponse(
        completion="".join(
            part.content for part in response.parts if isinstance(part, TextPart)
        ),
        finish_reason=response.finish_reason or "stop",
        tool_calls=tuple(
            ToolCall(
                id=part.tool_call_id,
                name=part.tool_name,
                arguments=part.args_as_json_str(),
            )
            for part in response.parts
            if isinstance(part, ToolCallPart)
        ),
        usage=_usage(response.usage),
        provider_state=response,
    )


def _usage(usage: RequestUsage) -> Usage:
    return Usage(
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
        cache_read_tokens=usage.cache_read_tokens,
    )


def _tool_definition(tool: ModelTool) -> ToolDefinition:
    return ToolDefinition(
        name=tool.name,
        description=tool.description or None,
        parameters_json_schema=tool.parameters,
    )


def _pydantic_messages(messages: Sequence[Message]) -> list[PydanticMessage]:
    instructions: str | None = None
    converted: list[PydanticMessage] = []
    for message in messages:
        match message:
            case SystemMessage():
                instructions = message.content
            case UserMessage():
                converted.append(
                    ModelRequest.user_text_prompt(
                        message.content,
                        instructions=instructions,
                    )
                )
            case AssistantMessage(provider_state=PydanticResponse() as state):
                converted.append(state)
            case AssistantMessage():
                parts = []
                if message.content:
                    parts.append(TextPart(message.content))
                parts.extend(
                    ToolCallPart(call.name, call.arguments, call.id)
                    for call in message.tool_calls
                )
                converted.append(PydanticResponse(parts=parts))
            case ToolResultMessage():
                converted.append(
                    ModelRequest(
                        parts=[
                            ToolReturnPart(
                                message.tool_name,
                                message.content,
                                message.tool_call_id,
                                outcome="failed" if message.is_error else "success",
                            )
                        ],
                        instructions=instructions,
                    )
                )
    return converted


def _text_delta(event: object) -> str:
    if isinstance(event, PartStartEvent) and isinstance(event.part, TextPart):
        return event.part.content
    if isinstance(event, PartDeltaEvent) and isinstance(event.delta, TextPartDelta):
        return event.delta.content_delta
    return ""
