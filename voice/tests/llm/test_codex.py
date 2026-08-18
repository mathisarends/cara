import asyncio
from typing import Protocol

from llm import (
    CodexModel,
    CodexReasoningEffort,
    OpenAIResponsesStreamEvent,
    StreamOutputItemAdded,
    StreamReasoningSummaryDelta,
    StreamTextDelta,
)
from voice.llm import AgentEvent, CodexAgentSession, TextDelta, TurnCompleted


class _CodexSession(Protocol):
    events: list[OpenAIResponsesStreamEvent]
    turns: list[str]
    args: tuple[object, ...]
    kwargs: dict[str, object]


def test_maps_shared_codex_session_to_agent_events(
    codex_session: _CodexSession,
) -> None:
    codex_session.events = [
        StreamReasoningSummaryDelta(delta="Thinking"),
        StreamOutputItemAdded(output_index=0, item={"type": "message"}),
        StreamTextDelta(delta="Hello"),
        StreamTextDelta(delta=""),
        StreamTextDelta(delta=" there"),
    ]
    session = CodexAgentSession()

    async def run() -> list[AgentEvent]:
        stream = await session.start_turn("Hi")
        events = [event async for event in stream]
        await session.steer("more")
        await session.interrupt()
        codex_session.events = [StreamTextDelta(delta="Again")]
        second_stream = await session.start_turn("Continue")
        assert [event async for event in second_stream] == [
            TextDelta("Again"),
            TurnCompleted(),
        ]
        return events

    events = asyncio.run(run())

    assert events == [TextDelta("Hello"), TextDelta(" there"), TurnCompleted()]
    assert codex_session.args == (CodexModel.SPARK,)
    assert codex_session.kwargs["reasoning_effort"] is CodexReasoningEffort.LOW
    assert "voice dialog" in str(codex_session.kwargs["instructions"])
    assert codex_session.turns == ["Hi", "Continue"]
