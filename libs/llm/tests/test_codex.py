from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from openai import AsyncOpenAI
from openai.types.responses import (
    Response,
    ResponseCompletedEvent,
    ResponseCreatedEvent,
)
from pydantic_ai.messages import (
    ModelRequest,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
)
from pydantic_ai.messages import (
    ModelResponse as PydanticResponse,
)
from pydantic_ai.providers.openai_codex import OpenAICodexProvider
from pydantic_ai.usage import RequestUsage

from llm import (
    AssistantMessage,
    CodexModel,
    CodexReasoningEffort,
    CodexTransport,
    ModelTool,
    PydanticAICodexModel,
    SystemMessage,
    ToolCall,
    ToolResultMessage,
    Usage,
    UserMessage,
    create_codex_model,
)
from llm.codex import _pydantic_messages
from llm.codex_transport import WebSocketUnavailable


def test_create_codex_model_uses_pydantic_ai_codex_provider() -> None:
    provider = object()
    model = object()
    responses_resource = object()
    with (
        patch("llm.codex.OpenAICodexProvider", return_value=provider),
        patch("llm.codex.OpenAICodexModel", return_value=model) as model_type,
        patch(
            "llm.codex.install_codex_responses_resource",
            return_value=responses_resource,
        ) as install_resource,
    ):
        created = create_codex_model(
            CodexModel.SOL,
            reasoning_effort=CodexReasoningEffort.HIGH,
        )

    assert isinstance(created, PydanticAICodexModel)
    install_resource.assert_called_once_with(provider)
    model_type.assert_called_once_with("gpt-5.6-sol", provider=provider)


async def test_invoke_returns_a_completion_without_streaming() -> None:
    model = _codex_model()
    model._model.request = AsyncMock(
        return_value=PydanticResponse(
            parts=[
                TextPart("Answer"),
                ToolCallPart("lookup", '{"key":"value"}', "call-1"),
            ],
            usage=RequestUsage(input_tokens=12, output_tokens=3, cache_read_tokens=8),
            finish_reason="tool_call",
        )
    )

    response = await model.invoke(
        [UserMessage(content="Question")],
        tools=[
            ModelTool(name="lookup", description="Look something up", parameters={})
        ],
    )

    assert response.completion == "Answer"
    assert response.finish_reason == "tool_call"
    assert response.tool_calls == (
        ToolCall(id="call-1", name="lookup", arguments='{"key":"value"}'),
    )
    assert response.usage == Usage(
        input_tokens=12, output_tokens=3, cache_read_tokens=8
    )
    assert response.usage.total_tokens == 15

    request_call = model._model.request.await_args
    assert request_call is not None
    _, _, request_parameters = request_call.args
    assert [tool.name for tool in request_parameters.function_tools] == ["lookup"]


async def test_websocket_failure_before_response_falls_back_to_http() -> None:
    provider = SimpleNamespace(client=SimpleNamespace(close=AsyncMock()))
    pydantic_model = SimpleNamespace(
        request=AsyncMock(
            side_effect=[
                WebSocketUnavailable("socket unavailable"),
                PydanticResponse(parts=[TextPart("HTTP answer")]),
            ]
        )
    )
    responses_resource = SimpleNamespace(
        aclose=AsyncMock(),
        prewarm=AsyncMock(),
        use_http=lambda: _http_mode(),
    )
    with (
        patch("llm.codex.OpenAICodexProvider", return_value=provider),
        patch("llm.codex.OpenAICodexModel", return_value=pydantic_model),
        patch(
            "llm.codex.install_codex_responses_resource",
            return_value=responses_resource,
        ),
    ):
        model = PydanticAICodexModel(
            CodexModel.SOL,
            transport=CodexTransport.WEBSOCKET,
        )

    response = await model.invoke([UserMessage(content="Question")])

    assert response.completion == "HTTP answer"
    assert pydantic_model.request.await_count == 2
    websocket_settings = pydantic_model.request.await_args_list[0].args[1]
    http_settings = pydantic_model.request.await_args_list[1].args[1]
    assert websocket_settings["openai_previous_response_id"] == "auto"
    assert "openai_previous_response_id" not in http_settings


async def test_prepare_warms_request_state_for_the_next_message() -> None:
    provider = SimpleNamespace(client=SimpleNamespace(close=AsyncMock()))
    warmup_response = PydanticResponse(
        parts=[],
        provider_name="openai-codex",
        provider_response_id="warmup-response",
    )
    pydantic_model = SimpleNamespace(
        request=AsyncMock(
            side_effect=[
                warmup_response,
                PydanticResponse(parts=[TextPart("Answer")]),
            ]
        )
    )
    responses_resource = SimpleNamespace(
        aclose=AsyncMock(),
        connection_generation=1,
        warmup_request=lambda: _http_mode(),
        use_http=lambda: _http_mode(),
    )
    with (
        patch("llm.codex.OpenAICodexProvider", return_value=provider),
        patch("llm.codex.OpenAICodexModel", return_value=pydantic_model),
        patch(
            "llm.codex.install_codex_responses_resource",
            return_value=responses_resource,
        ),
    ):
        model = PydanticAICodexModel(CodexModel.SOL)

    system = SystemMessage(content="System")
    await model.prepare([system])
    response = await model.invoke([system, UserMessage(content="Question")])

    assert response.completion == "Answer"
    warmup_messages = pydantic_model.request.await_args_list[0].args[0]
    assert len(warmup_messages) == 1
    assert isinstance(warmup_messages[0], ModelRequest)
    assert warmup_messages[0].instructions == "System"
    assert warmup_messages[0].parts == []
    request_messages = pydantic_model.request.await_args_list[1].args[0]
    request_settings = pydantic_model.request.await_args_list[1].args[1]
    assert len(request_messages) == 1
    assert isinstance(request_messages[0], ModelRequest)
    assert request_messages[0].instructions == "System"
    assert request_messages[0].parts[0].content == "Question"
    assert request_settings["openai_previous_response_id"] == "warmup-response"


async def test_prepare_uses_pydantic_ai_to_build_the_warmup_request() -> None:
    client = AsyncOpenAI(api_key="test")
    provider = OpenAICodexProvider(openai_client=client)
    response = Response.model_construct(
        id="warmup-response",
        created_at=0.0,
        model="gpt-5.6-sol",
        object="response",
        output=[],
        parallel_tool_calls=True,
        tool_choice="auto",
        tools=[],
        status="completed",
    )
    completed = ResponseCompletedEvent.model_construct(
        type="response.completed",
        sequence_number=1,
        response=response,
    )
    created = ResponseCreatedEvent.model_construct(
        type="response.created",
        sequence_number=0,
        response=response,
    )
    actual_response = Response.model_construct(
        id="actual-response",
        created_at=1.0,
        model="gpt-5.6-sol",
        object="response",
        output=[],
        parallel_tool_calls=True,
        tool_choice="auto",
        tools=[],
        status="completed",
    )
    actual_completed = ResponseCompletedEvent.model_construct(
        type="response.completed",
        sequence_number=2,
        response=actual_response,
    )
    connection = SimpleNamespace(
        close=AsyncMock(),
        recv=AsyncMock(side_effect=[created, completed, actual_completed]),
        response=SimpleNamespace(create=AsyncMock()),
        send=AsyncMock(),
    )
    with patch("llm.codex.OpenAICodexProvider", return_value=provider):
        model = PydanticAICodexModel(CodexModel.SOL)
    resource = model._responses_resource
    assert resource is not None
    resource._connection = connection
    resource._connection_generation = 1

    await model.prepare(
        [SystemMessage(content="System")],
        tools=[ModelTool(name="lookup", description="Look up", parameters={})],
    )

    sent = connection.send.await_args
    assert sent is not None
    request = sent.args[0]
    assert request["generate"] is False
    assert request["instructions"] == "System"
    assert request["input"] == [{"role": "user", "content": ""}]
    assert request["tools"][0]["name"] == "lookup"
    prepared_request = model._prepared_request
    assert prepared_request is not None
    assert prepared_request.response.provider_name == "openai-codex"
    assert prepared_request.response.provider_response_id == "warmup-response"

    await model.invoke(
        [
            SystemMessage(content="System"),
            UserMessage(content="Question"),
        ],
        tools=[ModelTool(name="lookup", description="Look up", parameters={})],
    )

    actual_request = connection.response.create.await_args
    assert actual_request is not None
    assert actual_request.kwargs["previous_response_id"] == "warmup-response"
    assert len(actual_request.kwargs["input"]) == 1
    assert actual_request.kwargs["input"][0]["role"] == "user"
    await model.aclose()


async def test_http_fallback_does_not_reuse_websocket_warmup_state() -> None:
    provider = SimpleNamespace(client=SimpleNamespace(close=AsyncMock()))
    warmup_response = PydanticResponse(
        parts=[],
        provider_name="openai-codex",
        provider_response_id="warmup-response",
    )
    pydantic_model = SimpleNamespace(
        request=AsyncMock(
            side_effect=[
                warmup_response,
                WebSocketUnavailable("socket unavailable"),
                PydanticResponse(parts=[TextPart("HTTP answer")]),
            ]
        )
    )
    responses_resource = SimpleNamespace(
        aclose=AsyncMock(),
        connection_generation=1,
        warmup_request=lambda: _http_mode(),
        use_http=lambda: _http_mode(),
    )
    with (
        patch("llm.codex.OpenAICodexProvider", return_value=provider),
        patch("llm.codex.OpenAICodexModel", return_value=pydantic_model),
        patch(
            "llm.codex.install_codex_responses_resource",
            return_value=responses_resource,
        ),
    ):
        model = PydanticAICodexModel(CodexModel.SOL)

    system = SystemMessage(content="System")
    await model.prepare([system])
    response = await model.invoke([system, UserMessage(content="Question")])

    assert response.completion == "HTTP answer"
    websocket_messages = pydantic_model.request.await_args_list[1].args[0]
    websocket_settings = pydantic_model.request.await_args_list[1].args[1]
    http_messages = pydantic_model.request.await_args_list[2].args[0]
    http_settings = pydantic_model.request.await_args_list[2].args[1]
    assert websocket_messages[0].parts[0].content == "Question"
    assert websocket_settings["openai_previous_response_id"] == "warmup-response"
    assert warmup_response not in http_messages
    assert "openai_previous_response_id" not in http_settings
    assert isinstance(http_messages[0], ModelRequest)
    assert http_messages[0].parts[0].content == "Question"


def test_messages_are_mapped_without_exposing_pydantic_ai_to_callers() -> None:
    messages = _pydantic_messages(
        [
            SystemMessage(content="System"),
            UserMessage(content="Question"),
            AssistantMessage(
                content="",
                tool_calls=(
                    ToolCall(id="call-1", name="lookup", arguments='{"key":"value"}'),
                ),
            ),
            ToolResultMessage(
                tool_call_id="call-1",
                tool_name="lookup",
                content="Answer",
            ),
        ]
    )

    user, assistant, tool_result = messages
    assert isinstance(user, ModelRequest)
    assert user.instructions == "System"
    assert isinstance(assistant, PydanticResponse)
    assert isinstance(assistant.parts[0], ToolCallPart)
    assert assistant.parts[0].tool_name == "lookup"
    assert isinstance(tool_result, ModelRequest)
    assert isinstance(tool_result.parts[0], ToolReturnPart)
    assert tool_result.parts[0].content == "Answer"


def test_provider_response_state_is_preserved_for_tool_followups() -> None:
    state = PydanticResponse(parts=[TextPart("partial")])

    assert _pydantic_messages(
        [AssistantMessage(content="partial", provider_state=state)]
    ) == [state]


def test_codex_enums_expose_configured_values() -> None:
    assert CodexModel.SOL.value == "gpt-5.6-sol"
    assert CodexReasoningEffort.XHIGH.value == "xhigh"


def _codex_model() -> PydanticAICodexModel:
    with (
        patch("llm.codex.OpenAICodexProvider"),
        patch("llm.codex.OpenAICodexModel"),
    ):
        return PydanticAICodexModel(
            CodexModel.SOL,
            transport=CodexTransport.HTTP,
        )


@asynccontextmanager
async def _http_mode() -> AsyncGenerator[None]:
    yield
