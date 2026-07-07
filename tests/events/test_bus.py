from __future__ import annotations

import asyncio

import pytest

from cara.events.bus import Event, EventBus


class SampleEvent(Event):
    pass


class OtherEvent(Event):
    pass


def test_dispatch_calls_subscribed_handler() -> None:
    bus = EventBus()
    received: list[SampleEvent] = []

    async def handler(event: SampleEvent) -> None:
        received.append(event)

    bus.subscribe(SampleEvent, handler)
    event = SampleEvent()

    result = asyncio.run(bus.dispatch(event))

    assert received == [event]
    assert result is event


def test_dispatch_without_subscribers_returns_event() -> None:
    bus = EventBus()
    event = SampleEvent()

    result = asyncio.run(bus.dispatch(event))

    assert result is event


def test_dispatch_only_calls_handlers_for_matching_type() -> None:
    bus = EventBus()
    sample_calls: list[SampleEvent] = []
    other_calls: list[OtherEvent] = []

    async def sample_handler(event: SampleEvent) -> None:
        sample_calls.append(event)

    async def other_handler(event: OtherEvent) -> None:
        other_calls.append(event)

    bus.subscribe(SampleEvent, sample_handler)
    bus.subscribe(OtherEvent, other_handler)

    asyncio.run(bus.dispatch(SampleEvent()))

    assert len(sample_calls) == 1
    assert other_calls == []


def test_dispatch_calls_all_handlers_for_same_type() -> None:
    bus = EventBus()
    calls: list[str] = []

    async def first(event: SampleEvent) -> None:
        calls.append("first")

    async def second(event: SampleEvent) -> None:
        calls.append("second")

    bus.subscribe(SampleEvent, first)
    bus.subscribe(SampleEvent, second)

    asyncio.run(bus.dispatch(SampleEvent()))

    assert set(calls) == {"first", "second"}


def test_wildcard_handler_receives_every_event_type() -> None:
    bus = EventBus()
    received: list[Event] = []

    async def handler(event: Event) -> None:
        received.append(event)

    bus.subscribe_all(handler)

    sample = SampleEvent()
    other = OtherEvent()
    asyncio.run(bus.dispatch(sample))
    asyncio.run(bus.dispatch(other))

    assert received == [sample, other]


def test_unsubscribe_stops_handler_from_receiving_events() -> None:
    bus = EventBus()
    calls: list[SampleEvent] = []

    async def handler(event: SampleEvent) -> None:
        calls.append(event)

    bus.subscribe(SampleEvent, handler)
    bus.unsubscribe(SampleEvent, handler)

    asyncio.run(bus.dispatch(SampleEvent()))

    assert calls == []


def test_unsubscribe_unknown_handler_is_a_noop() -> None:
    bus = EventBus()

    async def handler(event: SampleEvent) -> None:
        pass

    bus.unsubscribe(SampleEvent, handler)


def test_unsubscribe_all_stops_wildcard_handler() -> None:
    bus = EventBus()
    calls: list[Event] = []

    async def handler(event: Event) -> None:
        calls.append(event)

    bus.subscribe_all(handler)
    bus.unsubscribe_all(handler)

    asyncio.run(bus.dispatch(SampleEvent()))

    assert calls == []


def test_has_subscribers_reflects_specific_and_wildcard_subscriptions() -> None:
    bus = EventBus()
    assert bus.has_subscribers(SampleEvent) is False

    async def handler(event: SampleEvent) -> None:
        pass

    bus.subscribe(SampleEvent, handler)
    assert bus.has_subscribers(SampleEvent) is True
    assert bus.has_subscribers(OtherEvent) is False

    bus.unsubscribe(SampleEvent, handler)
    assert bus.has_subscribers(SampleEvent) is False

    async def wildcard(event: Event) -> None:
        pass

    bus.subscribe_all(wildcard)
    assert bus.has_subscribers(OtherEvent) is True


def test_dispatch_swallows_handler_exceptions_and_still_calls_others() -> None:
    bus = EventBus()
    calls: list[str] = []

    async def failing(event: SampleEvent) -> None:
        raise RuntimeError("boom")

    async def succeeding(event: SampleEvent) -> None:
        calls.append("ok")

    bus.subscribe(SampleEvent, failing)
    bus.subscribe(SampleEvent, succeeding)

    result = asyncio.run(bus.dispatch(SampleEvent()))

    assert calls == ["ok"]
    assert isinstance(result, SampleEvent)


def test_wait_for_event_returns_matching_dispatched_event() -> None:
    async def scenario() -> None:
        bus = EventBus()
        event = SampleEvent()

        waiter = asyncio.create_task(bus.wait_for_event(SampleEvent))
        await asyncio.sleep(0)

        await bus.dispatch(event)

        assert await waiter is event

    asyncio.run(scenario())


def test_wait_for_event_applies_predicate() -> None:
    async def scenario() -> None:
        bus = EventBus()

        waiter = asyncio.create_task(bus.wait_for_event(SampleEvent, predicate=lambda e: e.id == "wanted"))
        await asyncio.sleep(0)

        await bus.dispatch(SampleEvent(id="ignored"))
        await bus.dispatch(SampleEvent(id="wanted"))

        result = await waiter
        assert result.id == "wanted"

    asyncio.run(scenario())


def test_wait_for_event_times_out() -> None:
    async def scenario() -> None:
        bus = EventBus()
        with pytest.raises(TimeoutError):
            await bus.wait_for_event(SampleEvent, timeout=0.01)

    asyncio.run(scenario())


def test_wait_for_event_unsubscribes_after_resolving() -> None:
    async def scenario() -> None:
        bus = EventBus()
        event = SampleEvent()

        await asyncio.gather(bus.wait_for_event(SampleEvent), bus.dispatch(event))

        assert bus.has_subscribers(SampleEvent) is False

    asyncio.run(scenario())
