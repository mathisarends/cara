import asyncio
import logging
from collections.abc import AsyncIterator

from voice.events import (
    AssistantResponseRequested,
    AssistantResponseStarted,
    AssistantTextChunk,
    AssistantTextCompleted,
    AssistantToolCompleted,
    AssistantToolStarted,
)
from voice.events.bus import EventBus
from voice.events.models import VoiceTurnEnded, VoiceTurnStarted
from voice.llm import (
    AgentBridge,
    AgentEvent,
    TextDelta,
    ToolCompleted,
    ToolStarted,
    TurnCompleted,
)


class _AgentSession:
    def __init__(self) -> None:
        self.text: str | None = None
        self.lifecycle: list[str] = []

    async def prepare_turn(self) -> None:
        self.lifecycle.append("prepared")

    async def start_turn(self, text: str) -> AsyncIterator[AgentEvent]:
        self.text = text
        return self._events()

    async def _events(self) -> AsyncIterator[AgentEvent]:
        yield TextDelta("I will ")
        yield ToolStarted("weather")
        yield ToolCompleted("weather")
        yield TextDelta("")
        yield TextDelta("help")
        yield TurnCompleted()

    async def steer(self, text: str) -> None:
        pass

    async def finish_turn(self) -> None:
        self.lifecycle.append("finished")

    async def interrupt(self) -> None:
        pass


def test_agent_bridge_translates_every_agent_event(caplog) -> None:
    async def run() -> tuple[str | None, list[object], list[str]]:
        event_bus = EventBus()
        session = _AgentSession()
        AgentBridge(event_bus=event_bus, session=session)
        received: list[object] = []

        async def capture(event: object) -> None:
            received.append(event)

        event_bus.on(AssistantResponseStarted, capture)
        event_bus.on(AssistantTextChunk, capture)
        event_bus.on(AssistantToolStarted, capture)
        event_bus.on(AssistantToolCompleted, capture)
        event_bus.on(AssistantTextCompleted, capture)

        await event_bus.dispatch(VoiceTurnStarted(turn_id=7))
        await event_bus.request(
            AssistantResponseRequested(turn_id=7, text="What is the weather?")
        )
        await event_bus.dispatch(VoiceTurnEnded(turn_id=7))
        return session.text, received, session.lifecycle

    with caplog.at_level(logging.INFO, logger="voice.llm.bridge"):
        text, received, lifecycle = asyncio.run(run())

    assert text == "What is the weather?"
    assert received == [
        AssistantResponseStarted(turn_id=7),
        AssistantTextChunk(turn_id=7, chunk="I will "),
        AssistantToolStarted(turn_id=7, name="weather"),
        AssistantToolCompleted(turn_id=7, name="weather"),
        AssistantTextChunk(turn_id=7, chunk="help"),
        AssistantTextCompleted(turn_id=7, text="I will help"),
    ]
    assert caplog.messages == [
        "LLM input: What is the weather?",
        "LLM output: I will help",
    ]
    assert lifecycle == ["prepared", "finished"]
