import asyncio
from collections.abc import AsyncGenerator
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
    UserAudioChunk,
    WakeWordDetected,
)
from voice.events.bus import EventBus
from voice.vad import VoiceActivityDetector

_FORMAT = AudioFormat(sample_rate=16_000)


def test_wake_word_strategy_signals_detected_wake_words() -> None:
    async def run() -> list[BargeInSignal]:
        event_bus = EventBus()
        strategy = WakeWordBargeIn()
        strategy.set_context(_context(event_bus))

        await event_bus.emit(
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
    await event_bus.emit(UserAudioChunk(sequence=sequence, chunk=chunk))


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
