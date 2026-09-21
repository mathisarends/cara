import asyncio
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass
from enum import StrEnum
from uuid import uuid4

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

from llm.codex_transport import (
    CodexResponsesResource,
    WebSocketInterrupted,
    WebSocketUnavailable,
    install_codex_responses_resource,
)
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


class CodexTransport(StrEnum):
    HTTP = "http"
    WEBSOCKET = "websocket"


@dataclass(frozen=True, slots=True)
class _PreparedRequestState:
    messages: tuple[Message, ...]
    tools: tuple[ModelTool, ...]
    response: PydanticResponse
    connection_generation: int


class PydanticAICodexModel(ChatModel):
    """Pydantic AI adapter for Codex subscription authentication."""

    def __init__(
        self,
        model: CodexModel,
        *,
        reasoning_effort: CodexReasoningEffort | None = None,
        transport: CodexTransport = CodexTransport.WEBSOCKET,
    ) -> None:
        self._provider = OpenAICodexProvider()
        self._responses_resource: CodexResponsesResource | None = None
        if transport is CodexTransport.WEBSOCKET:
            self._responses_resource = install_codex_responses_resource(self._provider)
        self._model = OpenAICodexModel(model.value, provider=self._provider)
        session_id = str(uuid4())
        settings = OpenAIResponsesModelSettings(
            extra_headers={
                "session-id": session_id,
                "thread-id": session_id,
                "x-client-request-id": session_id,
            },
            openai_prompt_cache_key=session_id,
        )
        if reasoning_effort is not None:
            settings["openai_reasoning_effort"] = reasoning_effort.value
        self._http_settings = settings
        self._websocket_settings = OpenAIResponsesModelSettings(
            **settings,
            openai_previous_response_id="auto",
        )
        self._prepared_request: _PreparedRequestState | None = None
        self._prepared_request_lock = asyncio.Lock()

    async def prepare(
        self,
        messages: Sequence[Message],
        *,
        tools: Sequence[ModelTool] = (),
    ) -> None:
        resource = self._responses_resource
        if resource is None:
            return
        await self._clear_prepared_request()
        try:
            async with resource.warmup_request():
                response = await self._model.request(
                    _pydantic_messages(messages, ensure_request=True),
                    self._websocket_settings,
                    _request_parameters(tools),
                )
        except (WebSocketUnavailable, WebSocketInterrupted):
            return
        connection_generation = resource.connection_generation
        if response.provider_response_id is None or connection_generation is None:
            return
        prepared_request = _PreparedRequestState(
            messages=tuple(messages),
            tools=tuple(tools),
            response=response,
            connection_generation=connection_generation,
        )
        async with self._prepared_request_lock:
            self._prepared_request = prepared_request

    async def stream(
        self,
        messages: Sequence[Message],
        *,
        tools: Sequence[ModelTool] = (),
    ) -> AsyncIterator[ModelEvent]:
        if self._responses_resource is None:
            async for event in self._stream(messages, tools, websocket=False):
                yield event
            return
        emitted = False
        try:
            async for event in self._stream(messages, tools, websocket=True):
                emitted = True
                yield event
        except WebSocketUnavailable:
            if emitted:
                raise
            async for event in self._stream(messages, tools, websocket=False):
                yield event

    async def call(
        self,
        messages: Sequence[Message],
        *,
        tools: Sequence[ModelTool] = (),
    ) -> ModelResponse:
        if self._responses_resource is None:
            response = await self._request(messages, tools, websocket=False)
            return _model_response(response)
        try:
            response = await self._request(messages, tools, websocket=True)
        except WebSocketUnavailable:
            response = await self._request(messages, tools, websocket=False)
        return _model_response(response)

    async def aclose(self) -> None:
        if self._responses_resource is not None:
            await self._responses_resource.aclose()
        await self._provider.client.close()

    async def _stream(
        self,
        messages: Sequence[Message],
        tools: Sequence[ModelTool],
        *,
        websocket: bool,
    ) -> AsyncIterator[ModelEvent]:
        resource = self._responses_resource
        pydantic_messages, settings = await self._request_context(
            messages,
            tools,
            websocket=websocket,
        )
        if resource is not None and not websocket:
            async with resource.use_http():
                async for event in self._stream_response(
                    pydantic_messages,
                    tools,
                    settings,
                ):
                    yield event
            return
        async for event in self._stream_response(
            pydantic_messages,
            tools,
            settings,
        ):
            yield event

    async def _stream_response(
        self,
        messages: list[PydanticMessage],
        tools: Sequence[ModelTool],
        settings: OpenAIResponsesModelSettings,
    ) -> AsyncIterator[ModelEvent]:
        async with self._model.request_stream(
            messages,
            settings,
            _request_parameters(tools),
        ) as response:
            async for event in response:
                delta = _text_delta(event)
                if delta:
                    yield TextDelta(delta=delta)
            final = response.get()
        yield _model_response(final)

    async def _request(
        self,
        messages: Sequence[Message],
        tools: Sequence[ModelTool],
        *,
        websocket: bool,
    ) -> PydanticResponse:
        resource = self._responses_resource
        pydantic_messages, settings = await self._request_context(
            messages,
            tools,
            websocket=websocket,
        )
        if resource is None or websocket:
            return await self._model.request(
                pydantic_messages,
                settings,
                _request_parameters(tools),
            )
        async with resource.use_http():
            return await self._model.request(
                pydantic_messages,
                settings,
                _request_parameters(tools),
            )

    async def _request_context(
        self,
        messages: Sequence[Message],
        tools: Sequence[ModelTool],
        *,
        websocket: bool,
    ) -> tuple[list[PydanticMessage], OpenAIResponsesModelSettings]:
        if not websocket:
            return _pydantic_messages(messages), self._http_settings
        prepared_response = await self._take_prepared_response(messages, tools)
        if prepared_response is None:
            return _pydantic_messages(messages), self._websocket_settings
        prepared_length, response = prepared_response
        assert response.provider_response_id is not None
        settings = OpenAIResponsesModelSettings(**self._websocket_settings)
        settings["openai_previous_response_id"] = response.provider_response_id
        instructions = _latest_system_instruction(messages[:prepared_length])
        request_messages = _pydantic_messages(
            messages[prepared_length:],
            initial_instructions=instructions,
        )
        return request_messages, settings

    async def _take_prepared_response(
        self,
        messages: Sequence[Message],
        tools: Sequence[ModelTool],
    ) -> tuple[int, PydanticResponse] | None:
        async with self._prepared_request_lock:
            prepared_request = self._prepared_request
            self._prepared_request = None
        if prepared_request is None:
            return None
        prepared_length = len(prepared_request.messages)
        resource = self._responses_resource
        if (
            resource is None
            or resource.connection_generation != prepared_request.connection_generation
            or len(messages) <= prepared_length
            or tuple(messages[:prepared_length]) != prepared_request.messages
            or tuple(tools) != prepared_request.tools
        ):
            return None
        return prepared_length, prepared_request.response

    async def _clear_prepared_request(self) -> None:
        async with self._prepared_request_lock:
            self._prepared_request = None


def create_codex_model(
    model: CodexModel,
    *,
    reasoning_effort: CodexReasoningEffort | None = None,
    transport: CodexTransport = CodexTransport.WEBSOCKET,
) -> PydanticAICodexModel:
    return PydanticAICodexModel(
        model,
        reasoning_effort=reasoning_effort,
        transport=transport,
    )


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


def _pydantic_messages(
    messages: Sequence[Message],
    *,
    initial_instructions: str | None = None,
    ensure_request: bool = False,
) -> list[PydanticMessage]:
    instructions = initial_instructions
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
    if ensure_request:
        converted.append(ModelRequest(parts=[], instructions=instructions))
    return converted


def _latest_system_instruction(messages: Sequence[Message]) -> str | None:
    instructions = None
    for message in messages:
        if isinstance(message, SystemMessage):
            instructions = message.content
    return instructions


def _text_delta(event: object) -> str:
    if isinstance(event, PartStartEvent) and isinstance(event.part, TextPart):
        return event.part.content
    if isinstance(event, PartDeltaEvent) and isinstance(event.delta, TextPartDelta):
        return event.delta.content_delta
    return ""
