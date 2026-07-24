import asyncio

import pytest

from cara.events import (
    AssistantState,
    EventBus,
    SessionEnded,
    StateChanged,
    Transcribed,
)


def test_subscribe_infers_event_type_from_annotation() -> None:
    async def scenario() -> list[AssistantState]:
        bus = EventBus()
        received: list[AssistantState] = []

        async def handler(event: StateChanged) -> None:
            received.append(event.state)

        bus.subscribe(handler)
        await bus.dispatch(StateChanged(state=AssistantState.LISTENING))
        return received

    assert asyncio.run(scenario()) == [AssistantState.LISTENING]


def test_dispatch_only_calls_handlers_for_matching_type() -> None:
    async def scenario() -> tuple[int, int]:
        bus = EventBus()
        state_calls = 0
        transcribed_calls = 0

        async def on_state(event: StateChanged) -> None:
            nonlocal state_calls
            state_calls += 1

        async def on_transcribed(event: Transcribed) -> None:
            nonlocal transcribed_calls
            transcribed_calls += 1

        bus.subscribe(on_state)
        bus.subscribe(on_transcribed)
        await bus.dispatch(StateChanged(state=AssistantState.THINKING))
        return state_calls, transcribed_calls

    assert asyncio.run(scenario()) == (1, 0)


def test_dispatch_calls_all_handlers_for_same_type() -> None:
    async def scenario() -> set[str]:
        bus = EventBus()
        calls: set[str] = set()

        async def first(event: SessionEnded) -> None:
            calls.add("first")

        async def second(event: SessionEnded) -> None:
            calls.add("second")

        bus.subscribe(first)
        bus.subscribe(second)
        await bus.dispatch(SessionEnded())
        return calls

    assert asyncio.run(scenario()) == {"first", "second"}


def test_expect_returns_matching_dispatched_event() -> None:
    async def scenario() -> str:
        bus = EventBus()
        waiter = asyncio.create_task(bus.expect(Transcribed, where=lambda e: e.transcript == "wanted"))
        await asyncio.sleep(0)

        await bus.dispatch(Transcribed(transcript="ignored"))
        await bus.dispatch(Transcribed(transcript="wanted"))

        result = await waiter
        return result.transcript

    assert asyncio.run(scenario()) == "wanted"


def test_expect_times_out() -> None:
    async def scenario() -> None:
        bus = EventBus()
        with pytest.raises(TimeoutError):
            await bus.expect(Transcribed, timeout=0.01)

    asyncio.run(scenario())
