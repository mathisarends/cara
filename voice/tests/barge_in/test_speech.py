import asyncio
from collections.abc import AsyncGenerator, AsyncIterator
from typing import cast

import numpy as np

from voice.audio.models import AudioFormat
from voice.barge_in import (
    BargeInContext,
    BargeInSignal,
    BargeInStrategy,
    NoBargeIn,
    SpeechBargeIn,
    WakeWordBargeIn,
)
from voice.echo_cancellation import EchoPresence
from voice.events import (
    AssistantTurnStarted,
    SessionEnded,
    SessionStarted,
    UserAudioChunk,
    UserTranscriptionRequested,
    WakeWordDetected,
)
from voice.events.bus import EventBus
from voice.events.models import VoiceTurnInterrupted, VoiceTurnRequested
from voice.handler import BargeInHandler, TurnCoordinator, TurnListener
from voice.vad import VoiceActivityDetector

_FORMAT = AudioFormat(sample_rate=16_000)


class _Signals(BargeInStrategy):
    def __init__(self, *sequences: int) -> None:
        self._sequences = sequences
        self.drained = asyncio.Event()

    def set_context(self, context: BargeInContext) -> None:
        pass

    async def signals(self) -> AsyncIterator[BargeInSignal]:
        for sequence in self._sequences:
            yield BargeInSignal(sequence=sequence)
        self.drained.set()


def test_wake_word_strategy_signals_detected_wake_words() -> None:
    async def run() -> list[BargeInSignal]:
        event_bus = EventBus()
        strategy = WakeWordBargeIn()
        strategy.set_context(_context(event_bus))

        await event_bus.dispatch(
            WakeWordDetected(score=0.9, sequence=7, name="hey_mycroft")
        )
        return await _drain(strategy)

    assert asyncio.run(run()) == [BargeInSignal(sequence=7)]


def test_speech_strategy_signals_where_sustained_speech_started() -> None:
    async def run() -> list[BargeInSignal]:
        event_bus = EventBus()
        strategy = _speech_strategy(event_bus, _AlwaysSpeech())

        await _publish(event_bus, 1, _pcm(dbfs=-60.0, samples=1_024))
        await _publish(event_bus, 2, _pcm(dbfs=-20.0, samples=1_024))
        await _publish(event_bus, 3, _pcm(dbfs=-20.0, samples=1_024))
        return await _drain(strategy)

    assert asyncio.run(run()) == [BargeInSignal(sequence=2)]


def test_speech_strategy_ignores_speech_below_the_minimum_duration() -> None:
    async def run() -> list[BargeInSignal]:
        event_bus = EventBus()
        strategy = _speech_strategy(event_bus, _AlwaysSpeech())

        await _publish(event_bus, 1, _pcm(dbfs=-20.0, samples=1_024))
        await _publish(event_bus, 2, _pcm(dbfs=-60.0, samples=1_024))
        await _publish(event_bus, 3, _pcm(dbfs=-20.0, samples=1_024))
        return await _drain(strategy)

    assert asyncio.run(run()) == []


def test_speech_strategy_never_interrupts_on_the_assistants_own_voice() -> None:
    async def run() -> list[BargeInSignal]:
        event_bus = EventBus()
        # Loud, and speech by every measure the detector has - but it is the
        # assistant's own playback leaking through an imperfect canceller.
        echo = _Echo(confidence=0.8)
        strategy = _speech_strategy(event_bus, _AlwaysSpeech(), echo)

        for sequence in (1, 2, 3, 4):
            await _publish(event_bus, sequence, _pcm(dbfs=-20.0, samples=1_024))
        return await _drain(strategy)

    assert asyncio.run(run()) == []


def test_speech_strategy_interrupts_once_the_room_is_no_longer_just_playback() -> None:
    async def run() -> list[BargeInSignal]:
        event_bus = EventBus()
        echo = _Echo(confidence=0.8)
        strategy = _speech_strategy(event_bus, _AlwaysSpeech(), echo)

        await _publish(event_bus, 1, _pcm(dbfs=-20.0, samples=1_024))
        # The user speaks up, so the playback no longer explains the window.
        echo.confidence = 0.2
        await _publish(event_bus, 2, _pcm(dbfs=-20.0, samples=1_024))
        await _publish(event_bus, 3, _pcm(dbfs=-20.0, samples=1_024))
        return await _drain(strategy)

    assert asyncio.run(run()) == [BargeInSignal(sequence=2)]


def test_speech_strategy_keeps_loud_non_speech_from_interrupting() -> None:
    async def run() -> tuple[list[BargeInSignal], int]:
        event_bus = EventBus()
        detector = _NeverSpeech()
        strategy = _speech_strategy(event_bus, detector)

        for sequence in (1, 2, 3):
            await _publish(event_bus, sequence, _pcm(dbfs=-20.0, samples=1_024))
        return await _drain(strategy), detector.scored_windows

    signals, scored_windows = asyncio.run(run())

    assert signals == []
    assert scored_windows == 6


def test_speech_strategy_keeps_silence_away_from_the_detector() -> None:
    async def run() -> int:
        event_bus = EventBus()
        detector = _AlwaysSpeech()
        strategy = _speech_strategy(event_bus, detector)

        await _publish(event_bus, 1, _pcm(dbfs=-80.0, samples=1_024))
        await _drain(strategy)
        return detector.scored_windows

    assert asyncio.run(run()) == 0


def test_disabled_strategy_never_signals() -> None:
    async def run() -> list[BargeInSignal]:
        strategy = NoBargeIn()
        return [signal async for signal in strategy.signals()]

    assert asyncio.run(run()) == []


def test_barge_in_ignores_signals_outside_an_assistant_turn() -> None:
    async def run() -> list[object]:
        event_bus = EventBus()
        requests: list[object] = []
        strategy = _Signals(3)
        event_bus.on_request(VoiceTurnRequested, lambda event: _record(requests, event))
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

        event_bus.on_request(UserTranscriptionRequested, transcribe)
        event_bus.on(VoiceTurnInterrupted, lambda event: _record(events, event))
        strategy = _Signals(42)
        BargeInHandler(
            event_bus=event_bus,
            strategy=strategy,
            coordinator=coordinator,
        )

        await event_bus.request(VoiceTurnRequested(sequence=1))
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
    restarted = events[2]
    assert isinstance(restarted, UserTranscriptionRequested)
    assert restarted.turn_id == 2
    assert restarted.sequence == 42


class _AlwaysSpeech(VoiceActivityDetector):
    def __init__(self) -> None:
        self.scored_windows = 0

    @property
    def sample_rate(self) -> int:
        return _FORMAT.sample_rate

    @property
    def window_samples(self) -> int:
        return 512

    def speech_probability(self, window: bytes) -> float:
        self.scored_windows += 1
        return 1.0

    def reset(self) -> None:
        pass


class _NeverSpeech(_AlwaysSpeech):
    def speech_probability(self, window: bytes) -> float:
        super().speech_probability(window)
        return 0.0


class _Echo(EchoPresence):
    def __init__(self, confidence: float = 0.0) -> None:
        self.confidence = confidence

    @property
    def echo_confidence(self) -> float:
        return self.confidence


def _context(event_bus: EventBus, echo: EchoPresence | None = None) -> BargeInContext:
    return BargeInContext(
        event_bus=event_bus,
        audio_format=_FORMAT,
        echo_presence=echo or _Echo(),
    )


def _speech_strategy(
    event_bus: EventBus,
    detector: VoiceActivityDetector,
    echo: EchoPresence | None = None,
) -> SpeechBargeIn:
    strategy = SpeechBargeIn(
        detector=detector,
        min_level_dbfs=-40.0,
        min_speech_seconds=0.096,
    )
    strategy.set_context(_context(event_bus, echo))
    return strategy


async def _publish(event_bus: EventBus, sequence: int, chunk: bytes) -> None:
    await event_bus.dispatch(UserAudioChunk(sequence=sequence, chunk=chunk))


async def _drain(strategy: BargeInStrategy) -> list[BargeInSignal]:
    signals = cast(AsyncGenerator[BargeInSignal], strategy.signals())
    collected: list[BargeInSignal] = []
    try:
        while True:
            collected.append(await asyncio.wait_for(anext(signals), timeout=0.01))
    except TimeoutError:
        return collected
    finally:
        await signals.aclose()


def _pcm(*, dbfs: float, samples: int) -> bytes:
    amplitude = round(32_768.0 * 10 ** (dbfs / 20.0))
    return np.full(samples, amplitude, dtype=np.int16).tobytes()


async def _record(sink: list[object], event: object) -> None:
    sink.append(event)
