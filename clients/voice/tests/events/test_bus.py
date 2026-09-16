import asyncio

import pytest

from voice.events.bus import EventBus
from voice.events.errors import NoSubscriberError
from voice.events.models import Event, Request


def test_emit_runs_handlers_concurrently() -> None:
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

        emit = asyncio.create_task(bus.emit(Event()))
        await asyncio.wait_for(both_started.wait(), timeout=1.0)
        release.set()
        await emit

    asyncio.run(scenario())


def test_closing_a_subscription_stops_delivery() -> None:
    async def scenario() -> int:
        bus = EventBus()
        calls = 0

        async def handler(event: Event) -> None:
            nonlocal calls
            calls += 1

        subscription = bus.on(Event, handler)
        subscription.close()
        await bus.emit(Event())
        return calls

    assert asyncio.run(scenario()) == 0


def test_emit_without_subscribers_is_silent_by_default() -> None:
    asyncio.run(EventBus().emit(Event()))


def test_emit_without_subscribers_raises_when_required() -> None:
    with pytest.raises(NoSubscriberError, match="Event"):
        asyncio.run(EventBus().emit(Event(), require_subscribers=True))


def test_emit_runs_every_handler_despite_a_failure() -> None:
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
        with pytest.raises(RuntimeError, match="broken handler"):
            await bus.emit(Event())
        return successful_handler_ran

    assert asyncio.run(scenario()) is True


def test_emit_propagates_a_single_handler_failure_directly() -> None:
    async def scenario() -> None:
        bus = EventBus()

        async def handler(event: Event) -> None:
            raise RuntimeError("broke")

        bus.on(Event, handler)
        await bus.emit(Event())

    with pytest.raises(RuntimeError, match="broke"):
        asyncio.run(scenario())


def test_emit_reports_every_failing_handler_as_a_group() -> None:
    async def scenario() -> None:
        bus = EventBus()

        async def first(event: Event) -> None:
            raise RuntimeError("first broke")

        async def second(event: Event) -> None:
            raise ValueError("second broke")

        bus.on(Event, first)
        bus.on(Event, second)
        await bus.emit(Event())

    with pytest.raises(ExceptionGroup) as failure:
        asyncio.run(scenario())

    assert "Handlers failed for Event" in str(failure.value)
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
