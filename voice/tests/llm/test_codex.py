import asyncio
from typing import Protocol

from llmify import StreamTextDelta

from voice.llm import AgentEvent, CodexAgentSession, TextDelta, TurnCompleted


class _CodexBackend(Protocol):
    events: list[object]
    config: dict[str, object]
    messages: list[list["_Message"]]


class _Message(Protocol):
    content: object


def test_streams_text_and_retains_the_completed_conversation(
    codex_backend: _CodexBackend,
) -> None:
    codex_backend.events = [
        object(),
        StreamTextDelta(delta=""),
        StreamTextDelta(delta="Hello"),
        StreamTextDelta(delta=" there"),
    ]
    session = CodexAgentSession(model="test-model")

    async def run() -> list[AgentEvent]:
        stream = await session.start_turn("Hi")
        events = [event async for event in stream]
        await session.steer("more")
        await session.interrupt()
        codex_backend.events = [StreamTextDelta(delta="Again")]
        second_stream = await session.start_turn("Continue")
        assert [event async for event in second_stream] == [
            TextDelta("Again"),
            TurnCompleted(),
        ]
        return events

    events = asyncio.run(run())

    assert events == [TextDelta("Hello"), TextDelta(" there"), TurnCompleted()]
    assert codex_backend.config["model"] == "test-model"
    assert codex_backend.config["reasoning_effort"] == "low"
    assert [message.content for message in codex_backend.messages[0]] == [
        codex_backend.messages[1][0].content,
        "Hi",
    ]
    assert [message.content for message in codex_backend.messages[1]][1:] == [
        "Hi",
        "Hello there",
        "Continue",
    ]
