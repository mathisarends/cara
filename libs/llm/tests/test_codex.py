from unittest.mock import patch

from pydantic_ai.messages import (
    ModelRequest,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
)
from pydantic_ai.messages import (
    ModelResponse as PydanticResponse,
)

from llm import (
    AssistantMessage,
    CodexModel,
    CodexReasoningEffort,
    PydanticAICodexModel,
    SystemMessage,
    ToolCall,
    ToolResultMessage,
    UserMessage,
    create_codex_model,
)
from llm.codex import _pydantic_messages


def test_create_codex_model_uses_pydantic_ai_codex_provider() -> None:
    provider = object()
    model = object()
    with (
        patch("llm.codex.OpenAICodexProvider", return_value=provider),
        patch("llm.codex.OpenAICodexModel", return_value=model) as model_type,
    ):
        created = create_codex_model(
            CodexModel.SOL,
            reasoning_effort=CodexReasoningEffort.HIGH,
        )

    assert isinstance(created, PydanticAICodexModel)
    model_type.assert_called_once_with("gpt-5.6-sol", provider=provider)


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
