import asyncio
from pathlib import Path
from typing import Protocol
from unittest.mock import patch

from llmify import (
    ChatCodex,
    ContinuationMode,
    Function,
    PromptCacheOptions,
    StreamOutputItemAdded,
    StreamReasoningSummaryDelta,
    StreamTextDelta,
    StreamToolCall,
    ToolCall,
)

from llm import OpenAIResponsesStreamEvent
from llm.codex import (
    CodexModel,
    CodexReasoningEffort,
    CodexSession,
    create_codex_model,
)


class _CodexBackend(Protocol):
    events: list[OpenAIResponsesStreamEvent]
    messages: list[list["_Message"]]
    stream_options: list[dict[str, object]]


class _Message(Protocol):
    content: object
    tool_calls: list[ToolCall]


def test_create_codex_model_configures_responses_features() -> None:
    with patch.object(ChatCodex, "from_cli", return_value=object()) as from_cli:
        create_codex_model(
            CodexModel.LUNA,
            auth_path=Path("auth.json"),
            max_tokens=1_000,
            temperature=0.2,
            top_p=0.8,
            reasoning_effort=CodexReasoningEffort.HIGH,
            reasoning={"context": "all_turns"},
            store=True,
            continuation_mode=ContinuationMode.PREVIOUS_RESPONSE_ID,
            preserve_reasoning=False,
            reasoning_summary="detailed",
            prompt_cache_key="custom-cache",
            prompt_cache_options=PromptCacheOptions(mode="explicit", ttl="30m"),
            timeout=15.0,
            max_retries=4,
            default_headers={"X-Test": "yes"},
            parallel_tool_calls=False,
        )

    options = from_cli.call_args.kwargs
    assert options["model"] == "gpt-5.6-luna"
    assert options["auth_path"] == Path("auth.json")
    assert options["max_tokens"] == 1_000
    assert options["temperature"] == 0.2
    assert options["top_p"] == 0.8
    assert options["reasoning_effort"] == "high"
    assert options["reasoning"] == {"context": "all_turns"}
    assert options["continuation_mode"] == "previous_response_id"
    assert options["preserve_reasoning"] is False
    assert options["reasoning_summary"] == "detailed"
    assert options["prompt_cache_key"] == "custom-cache"
    assert options["prompt_cache_options"] == PromptCacheOptions(
        mode="explicit", ttl="30m"
    )
    assert options["store"] is True
    assert options["timeout"] == 15.0
    assert options["max_retries"] == 4
    assert options["default_headers"] == {"X-Test": "yes"}
    assert options["parallel_tool_calls"] is False


def test_create_codex_model_omits_optional_reasoning_payload() -> None:
    with patch.object(ChatCodex, "from_cli", return_value=object()) as from_cli:
        create_codex_model(CodexModel.SPARK)

    options = from_cli.call_args.kwargs
    assert options["reasoning_effort"] is None
    assert options["reasoning_summary"] is None
    assert "reasoning" not in options


def test_codex_enums_expose_the_supported_configuration_values() -> None:
    assert {model.value for model in CodexModel} == {
        "gpt-5.3-codex-spark",
        "gpt-5.6-luna",
        "gpt-5.6-terra",
        "gpt-5.6-sol",
    }
    assert {effort.value for effort in CodexReasoningEffort} == {
        "none",
        "minimal",
        "low",
        "medium",
        "high",
        "xhigh",
        "max",
    }


def test_session_streams_text_and_retains_conversation(
    codex_backend: _CodexBackend,
) -> None:
    tool_call = ToolCall(
        id="call-1",
        function=Function(name="lights", arguments="{}"),
    )
    codex_backend.events = [
        StreamReasoningSummaryDelta(delta="Thinking"),
        StreamOutputItemAdded(output_index=0, item={"type": "message"}),
        StreamTextDelta(delta=""),
        StreamTextDelta(delta="Hello"),
        StreamTextDelta(delta=" there"),
        StreamToolCall(tool_call=tool_call),
    ]
    session = CodexSession(instructions="Be concise.")

    async def run() -> tuple[
        list[OpenAIResponsesStreamEvent], list[OpenAIResponsesStreamEvent]
    ]:
        first = [event async for event in session.stream("Hi", tool_choice="none")]
        codex_backend.events = [StreamTextDelta(delta="Again")]
        second = [event async for event in session.stream("Continue")]
        return first, second

    first, second = asyncio.run(run())

    assert first == [
        StreamReasoningSummaryDelta(delta="Thinking"),
        StreamOutputItemAdded(output_index=0, item={"type": "message"}),
        StreamTextDelta(delta=""),
        StreamTextDelta(delta="Hello"),
        StreamTextDelta(delta=" there"),
        StreamToolCall(tool_call=tool_call),
    ]
    assert second == [StreamTextDelta(delta="Again")]
    assert [message.content for message in codex_backend.messages[0]] == [
        "Be concise.",
        "Hi",
    ]
    assert [message.content for message in codex_backend.messages[1]] == [
        "Be concise.",
        "Hi",
        "Hello there",
        "Continue",
    ]
    assert codex_backend.messages[1][2].tool_calls == [tool_call]
    assert codex_backend.stream_options == [{"tool_choice": "none"}, {}]
