import asyncio
from typing import Protocol
from unittest.mock import patch

from llmify import ChatCodex, HTTPResponsesTransport, StreamTextDelta

from llm.codex import (
    CodexModel,
    CodexReasoningEffort,
    CodexSession,
    create_codex_model,
)


class _CodexBackend(Protocol):
    events: list[object]
    messages: list[list["_Message"]]


class _Message(Protocol):
    content: object


def test_create_codex_model_configures_responses_features() -> None:
    with patch.object(ChatCodex, "from_cli", return_value=object()) as from_cli:
        create_codex_model(CodexModel.SOL, CodexReasoningEffort.HIGH)

    options = from_cli.call_args.kwargs
    assert options["model"] == "gpt-5.6-sol"
    assert options["reasoning_effort"] == "high"
    assert options["reasoning_summary"] == "auto"
    assert options["reasoning"] == {"context": "all_turns"}
    assert options["continuation_mode"] == "previous_response_id"
    assert options["preserve_reasoning"] is True
    assert options["prompt_cache_key"] == "cara"
    assert isinstance(options["transport"], HTTPResponsesTransport)


def test_codex_enums_expose_the_supported_configuration_values() -> None:
    assert {model.value for model in CodexModel} == {
        "gpt-5.3-codex-spark",
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
    codex_backend.events = [
        object(),
        StreamTextDelta(delta=""),
        StreamTextDelta(delta="Hello"),
        StreamTextDelta(delta=" there"),
    ]
    session = CodexSession(instructions="Be concise.")

    async def run() -> tuple[list[str], list[str]]:
        first = [delta async for delta in session.stream("Hi")]
        codex_backend.events = [StreamTextDelta(delta="Again")]
        second = [delta async for delta in session.stream("Continue")]
        return first, second

    first, second = asyncio.run(run())

    assert first == ["Hello", " there"]
    assert second == ["Again"]
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
