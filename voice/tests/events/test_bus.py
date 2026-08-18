import asyncio
import logging

import pytest

from voice.events.bus import EventBus
from voice.events.models import Event, Request


def test_dispatch_runs_handlers_concurrently() -> None:
    async def scenario() -> None:
        bus = EventBus()
        release = asyncio.Event()
        both_started = asyncio.Event()
        started = 0

        async def handler(event: Event) -> None:
            nonlocal started
            started += 1
            if started == 2:
                both_started.set()
            await release.wait()

        bus.on(Event, handler)
        bus.on(Event, handler)

        dispatch = asyncio.create_task(bus.dispatch(Event()))
        await asyncio.wait_for(both_started.wait(), timeout=1.0)
        release.set()
        await dispatch

    asyncio.run(scenario())


def test_off_removes_handler() -> None:
    async def scenario() -> int:
        bus = EventBus()
        calls = 0

        async def handler(event: Event) -> None:
            nonlocal calls
            calls += 1

        bus.on(Event, handler)
        bus.off(Event, handler)
        await bus.dispatch(Event())
        return calls

    assert asyncio.run(scenario()) == 0


def test_handler_failure_does_not_cancel_other_handlers(caplog) -> None:
    async def scenario() -> bool:
        bus = EventBus()
        successful_handler_ran = False

        async def failing_handler(event: Event) -> None:
            raise RuntimeError("broken handler")

        async def successful_handler(event: Event) -> None:
            nonlocal successful_handler_ran
            successful_handler_ran = True

        bus.on(Event, failing_handler)
        bus.on(Event, successful_handler)
        await bus.dispatch(Event())
        return successful_handler_ran

    with caplog.at_level(logging.ERROR, logger="voice.events.bus"):
        assert asyncio.run(scenario()) is True

    assert "Event handler failed for Event" in caplog.text


def test_raise_if_failed_is_silent_when_every_handler_succeeds() -> None:
    async def scenario() -> None:
        bus = EventBus()

        async def handler(event: Event) -> None:
            return None

        bus.on(Event, handler)
        dispatch = await bus.dispatch(Event())
        dispatch.raise_if_failed()

    asyncio.run(scenario())


def test_raise_if_failed_reports_every_failing_handler() -> None:
    async def scenario() -> None:
        bus = EventBus()

        async def first(event: Event) -> None:
            raise RuntimeError("first broke")

        async def second(event: Event) -> None:
            raise ValueError("second broke")

        bus.on(Event, first)
        bus.on(Event, second)
        dispatch = await bus.dispatch(Event())
        dispatch.raise_if_failed()

    with pytest.raises(ExceptionGroup) as failure:
        asyncio.run(scenario())

    assert "Listeners failed for Event" in str(failure.value)
    assert [type(error) for error in failure.value.exceptions] == [
        RuntimeError,
        ValueError,
    ]


def test_request_propagates_handler_failures() -> None:
    async def scenario() -> None:
        bus = EventBus()

        async def handler(request: Request) -> None:
            raise RuntimeError("handler broke")

        bus.on_request(Request, handler)
        await bus.request(Request())

    with pytest.raises(RuntimeError, match="handler broke"):
        asyncio.run(scenario())


def test_request_without_a_handler_is_a_wiring_error() -> None:
    with pytest.raises(LookupError, match="Request"):
        asyncio.run(EventBus().request(Request()))


def test_a_request_type_accepts_only_one_handler() -> None:
    bus = EventBus()

    async def handler(request: Request) -> None:
        return None

    bus.on_request(Request, handler)

    with pytest.raises(RuntimeError, match="already has a handler"):
        bus.on_request(Request, handler)
