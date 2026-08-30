import asyncio

from voice.events import (
    AssistantResponseStarted,
    AssistantTextChunk,
    AssistantToolStarted,
)
from voice.events.bus import EventBus
from voice.events.models import VoiceTurnEnded
from voice.handler import ToolAcknowledgementListener


def test_speaks_ack_when_tool_call_follows_silence(monkeypatch) -> None:
    async def run() -> list[AssistantTextChunk]:
        event_bus = EventBus()
        ToolAcknowledgementListener(event_bus=event_bus)
        chunks: list[AssistantTextChunk] = []

        async def capture(event: AssistantTextChunk) -> None:
            chunks.append(event)

        event_bus.on(AssistantTextChunk, capture)

        await event_bus.dispatch(AssistantResponseStarted(turn_id=3))
        await event_bus.dispatch(AssistantToolStarted(turn_id=3, name="weather"))
        await event_bus.dispatch(AssistantToolStarted(turn_id=3, name="calendar"))
        return chunks

    monkeypatch.setattr(
        "voice.handler.tool_acknowledgement.random.choice",
        lambda choices: choices[0],
    )

    assert asyncio.run(run()) == [AssistantTextChunk(turn_id=3, chunk="On it.")]


def test_stays_silent_when_assistant_already_spoke() -> None:
    async def run() -> list[AssistantTextChunk]:
        event_bus = EventBus()
        ToolAcknowledgementListener(event_bus=event_bus)
        chunks: list[AssistantTextChunk] = []

        async def capture(event: AssistantTextChunk) -> None:
            chunks.append(event)

        event_bus.on(AssistantTextChunk, capture)

        await event_bus.dispatch(AssistantResponseStarted(turn_id=4))
        await event_bus.dispatch(AssistantTextChunk(turn_id=4, chunk="I'll check."))
        await event_bus.dispatch(AssistantToolStarted(turn_id=4, name="weather"))
        return chunks

    assert asyncio.run(run()) == [AssistantTextChunk(turn_id=4, chunk="I'll check.")]


def test_resets_state_and_avoids_repeating_the_last_ack(monkeypatch) -> None:
    async def run() -> list[AssistantTextChunk]:
        event_bus = EventBus()
        ToolAcknowledgementListener(event_bus=event_bus)
        chunks: list[AssistantTextChunk] = []

        async def capture(event: AssistantTextChunk) -> None:
            chunks.append(event)

        event_bus.on(AssistantTextChunk, capture)

        for turn_id in (5, 6):
            await event_bus.dispatch(AssistantResponseStarted(turn_id=turn_id))
            await event_bus.dispatch(
                AssistantToolStarted(turn_id=turn_id, name="weather")
            )
            await event_bus.dispatch(VoiceTurnEnded(turn_id=turn_id))
        return chunks

    monkeypatch.setattr(
        "voice.handler.tool_acknowledgement.random.choice",
        lambda choices: choices[0],
    )

    assert asyncio.run(run()) == [
        AssistantTextChunk(turn_id=5, chunk="On it."),
        AssistantTextChunk(turn_id=6, chunk="Let me check."),
    ]
