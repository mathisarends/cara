import asyncio
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

    async def interrupt(self) -> None:
        pass


def test_agent_bridge_translates_every_agent_event() -> None:
    async def run() -> tuple[str | None, list[object]]:
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

        await event_bus.dispatch(
            AssistantResponseRequested(turn_id=7, text="What is the weather?")
        )
        return session.text, received

    text, received = asyncio.run(run())

    assert text == "What is the weather?"
    assert received == [
        AssistantResponseStarted(turn_id=7),
        AssistantTextChunk(turn_id=7, chunk="I will "),
        AssistantToolStarted(turn_id=7, name="weather"),
        AssistantToolCompleted(turn_id=7, name="weather"),
        AssistantTextChunk(turn_id=7, chunk="help"),
        AssistantTextCompleted(turn_id=7, text="I will help"),
    ]
