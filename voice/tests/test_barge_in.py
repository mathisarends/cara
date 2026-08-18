import asyncio
from collections.abc import AsyncIterator

from voice.barge_in import BargeInSignal, NoBargeIn, WakeWordBargeIn
from voice.events import (
    AssistantTurnStarted,
    SessionEnded,
    SessionStarted,
    UserTranscriptionRequested,
    WakeWordDetected,
)
from voice.events.bus import EventBus
from voice.events.models import VoiceTurnInterrupted, VoiceTurnRequested
from voice.handler import BargeInHandler, TurnCoordinator, TurnListener


class _Signals:
    """Feeds pre-recorded signals into a handler and reports when it drained."""

    def __init__(self, *sequences: int) -> None:
        self._sequences = sequences
        self.drained = asyncio.Event()

    async def signals(self) -> AsyncIterator[BargeInSignal]:
        for sequence in self._sequences:
            yield BargeInSignal(sequence=sequence)
        self.drained.set()


def test_wake_word_strategy_signals_detected_wake_words() -> None:
    async def run() -> list[BargeInSignal]:
        event_bus = EventBus()
        strategy = WakeWordBargeIn(event_bus=event_bus)

        await event_bus.dispatch(
            WakeWordDetected(score=0.9, sequence=7, name="hey_mycroft")
        )
        signals = strategy.signals()
        try:
            return [await anext(signals)]
        finally:
            await signals.aclose()

    assert asyncio.run(run()) == [BargeInSignal(sequence=7)]


def test_disabled_strategy_never_signals() -> None:
    async def run() -> list[BargeInSignal]:
        return [signal async for signal in NoBargeIn().signals()]

    assert asyncio.run(run()) == []


def test_barge_in_ignores_signals_outside_an_assistant_turn() -> None:
    async def run() -> list[object]:
        event_bus = EventBus()
        requests: list[object] = []
        strategy = _Signals(3)
        event_bus.on(VoiceTurnRequested, lambda event: _record(requests, event))
        BargeInHandler(
            event_bus=event_bus,
            strategy=strategy,
            coordinator=TurnCoordinator(),
        )

        await event_bus.dispatch(SessionStarted())
        await strategy.drained.wait()
        await event_bus.dispatch(SessionEnded())
        return requests

    assert asyncio.run(run()) == []


def test_barge_in_restarts_the_turn_at_the_signalled_audio_position() -> None:
    async def run() -> list[object]:
        event_bus = EventBus()
        coordinator = TurnCoordinator()
        TurnListener(event_bus=event_bus, coordinator=coordinator)
        events: list[object] = []
        transcribing = asyncio.Event()

        async def transcribe(event: UserTranscriptionRequested) -> None:
            events.append(event)
            transcribing.set()
            await asyncio.Event().wait()

        event_bus.on(UserTranscriptionRequested, transcribe)
        event_bus.on(VoiceTurnInterrupted, lambda event: _record(events, event))
        strategy = _Signals(42)
        BargeInHandler(
            event_bus=event_bus,
            strategy=strategy,
            coordinator=coordinator,
        )

        await event_bus.dispatch(VoiceTurnRequested(sequence=1))
        await transcribing.wait()
        await event_bus.dispatch(AssistantTurnStarted())
        await event_bus.dispatch(SessionStarted())
        await strategy.drained.wait()
        await coordinator.close()
        return events

    events = asyncio.run(run())

    assert [type(event) for event in events] == [
        UserTranscriptionRequested,
        VoiceTurnInterrupted,
        UserTranscriptionRequested,
    ]
    assert events[1] == VoiceTurnInterrupted(turn_id=1)
    assert events[2].turn_id == 2
    assert events[2].sequence == 42


async def _record(sink: list[object], event: object) -> None:
    sink.append(event)
