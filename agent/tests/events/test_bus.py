import asyncio

import pytest
from transitbus import EventBus

from agent.events import (
    SessionEnded,
    SessionStarted,
    UserSpeechEnded,
    UserSpeechStarted,
)


def test_subscribe_infers_event_type_from_annotation() -> None:
    async def scenario() -> int:
        bus = EventBus()
        calls = 0

        async def handler(event: UserSpeechStarted) -> None:
            nonlocal calls
            calls += 1

        bus.subscribe(handler)
        await bus.dispatch(UserSpeechStarted())
        return calls

    assert asyncio.run(scenario()) == 1


def test_dispatch_only_calls_handlers_for_matching_type() -> None:
    async def scenario() -> tuple[int, int]:
        bus = EventBus()
        started_calls = 0
        ended_calls = 0

        async def on_started(event: UserSpeechStarted) -> None:
            nonlocal started_calls
            started_calls += 1

        async def on_ended(event: UserSpeechEnded) -> None:
            nonlocal ended_calls
            ended_calls += 1

        bus.subscribe(on_started)
        bus.subscribe(on_ended)
        await bus.dispatch(UserSpeechStarted())
        return started_calls, ended_calls

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
    async def scenario() -> SessionStarted:
        bus = EventBus()
        waiter = asyncio.create_task(bus.expect(SessionStarted))
        await asyncio.sleep(0)

        event = SessionStarted()
        await bus.dispatch(event)
        return await waiter

    assert isinstance(asyncio.run(scenario()), SessionStarted)


def test_expect_times_out() -> None:
    async def scenario() -> None:
        bus = EventBus()
        with pytest.raises(TimeoutError):
            await bus.expect(SessionStarted, timeout=0.01)

    asyncio.run(scenario())
