import asyncio
from collections.abc import AsyncIterator

import pytest

from voice.activation import (
    Activation,
    ActivationCoordinator,
    ActivationSource,
    ExternalActivationSource,
    ListenActivation,
    PromptActivation,
)
from voice.events import SessionStarted
from voice.events.bus import EventBus
from voice.events.models import (
    PromptTurnRequested,
    Request,
    VoiceTurnEnded,
    VoiceTurnRequested,
    VoiceTurnStarted,
)


class _FixedSource(ActivationSource):
    def __init__(self, *activations: Activation) -> None:
        self._activations = activations

    async def activations(self) -> AsyncIterator[Activation]:
        for activation in self._activations:
            yield activation


class _FailingSource(ActivationSource):
    async def activations(self) -> AsyncIterator[Activation]:
        raise RuntimeError("microphone is gone")
        yield  # unreachable, but keeps this a generator


class _NeverEndingSource(ActivationSource):
    async def activations(self) -> AsyncIterator[Activation]:
        await asyncio.Event().wait()
        yield  # unreachable, but keeps this a generator


def _collect_requests(event_bus: EventBus) -> list[Request]:
    requests: list[Request] = []

    async def start_turn(event: Request) -> None:
        requests.append(event)
        await event_bus.dispatch(VoiceTurnStarted(turn_id=len(requests)))

    event_bus.on_request(VoiceTurnRequested, start_turn)
    event_bus.on_request(PromptTurnRequested, start_turn)
    return requests


async def _wait_for_requests(requests: list[Request], *, count: int) -> None:
    async with asyncio.timeout(1.0):
        while len(requests) < count:
            await asyncio.sleep(0)


def test_starts_no_second_turn_while_one_is_active() -> None:
    async def run() -> list[Request]:
        event_bus = EventBus()
        requests = _collect_requests(event_bus)
        coordinator = ActivationCoordinator(
            event_bus=event_bus,
            sources=(
                _FixedSource(
                    ListenActivation(sequence=1), ListenActivation(sequence=2)
                ),
            ),
        )

        await event_bus.dispatch(SessionStarted())
        await coordinator.run()
        return requests

    assert [event.sequence for event in asyncio.run(run())] == [1]


def test_starts_a_turn_again_once_the_previous_one_ended() -> None:
    async def run() -> list[Request]:
        event_bus = EventBus()
        requests = _collect_requests(event_bus)
        source = ExternalActivationSource()
        coordinator = ActivationCoordinator(
            event_bus=event_bus,
            sources=(source, _NeverEndingSource()),
        )
        await event_bus.dispatch(SessionStarted())
        running = asyncio.create_task(coordinator.run())

        await source.activate()
        await _wait_for_requests(requests, count=1)
        await event_bus.dispatch(VoiceTurnEnded(turn_id=1))
        await source.activate(speech_start_timeout=4.0)
        await _wait_for_requests(requests, count=2)

        running.cancel()
        await asyncio.gather(running, return_exceptions=True)
        return requests

    requests = asyncio.run(run())

    assert [event.sequence for event in requests] == [None, None]
    assert [event.speech_start_timeout for event in requests] == [None, 4.0]


def test_turns_a_prompt_activation_into_a_prompt_turn() -> None:
    async def run() -> list[Request]:
        event_bus = EventBus()
        requests = _collect_requests(event_bus)
        coordinator = ActivationCoordinator(
            event_bus=event_bus,
            sources=(_FixedSource(PromptActivation(prompt="The laundry is done")),),
        )

        await event_bus.dispatch(SessionStarted())
        await coordinator.run()
        return requests

    assert asyncio.run(run()) == [PromptTurnRequested(prompt="The laundry is done")]


def test_ignores_activations_before_the_session_starts() -> None:
    async def run() -> list[Request]:
        event_bus = EventBus()
        requests = _collect_requests(event_bus)
        coordinator = ActivationCoordinator(
            event_bus=event_bus,
            sources=(_FixedSource(ListenActivation(sequence=1)),),
        )

        await coordinator.run()
        return requests

    assert asyncio.run(run()) == []


def test_stops_every_source_once_the_first_one_ends() -> None:
    async def run() -> None:
        event_bus = EventBus()
        _collect_requests(event_bus)
        coordinator = ActivationCoordinator(
            event_bus=event_bus,
            sources=(_FixedSource(), _NeverEndingSource()),
        )

        await event_bus.dispatch(SessionStarted())
        await asyncio.wait_for(coordinator.run(), timeout=1.0)

    asyncio.run(run())


def test_reports_a_failing_source() -> None:
    async def run() -> None:
        event_bus = EventBus()
        coordinator = ActivationCoordinator(
            event_bus=event_bus,
            sources=(_FailingSource(), _NeverEndingSource()),
        )

        await event_bus.dispatch(SessionStarted())
        await asyncio.wait_for(coordinator.run(), timeout=1.0)

    with pytest.raises(RuntimeError, match="microphone is gone"):
        asyncio.run(run())


def test_rejects_a_session_without_any_source() -> None:
    with pytest.raises(ValueError, match="at least one activation source"):
        ActivationCoordinator(event_bus=EventBus(), sources=())
