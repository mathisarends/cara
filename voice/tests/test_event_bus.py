import asyncio
import logging

from voice.events.bus import EventBus
from voice.events.models import Event


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
