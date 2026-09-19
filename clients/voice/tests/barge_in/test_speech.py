import asyncio
from collections.abc import AsyncIterator

import numpy as np

from voice.activation import ActivationKind, ListenActivation
from voice.audio import AudioFormat, AudioFrame, AudioFrameSource
from voice.barge_in import (
    BargeInSignal,
    BargeInStrategy,
    NoBargeIn,
    SpeechBargeIn,
    WakeWordBargeIn,
)
from voice.vad import VoiceActivityDetector

_FORMAT = AudioFormat(sample_rate=16_000)
_LOUD = -20.0


def test_wake_word_strategy_interrupts_on_wake_word_activations_only() -> None:
    strategy = WakeWordBargeIn()

    assert strategy.interruption_for(
        ListenActivation(sequence=7, kind=ActivationKind.WAKE_WORD)
    ) == BargeInSignal(sequence=7)
    assert strategy.interruption_for(ListenActivation(sequence=7)) is None


def test_speech_strategy_signals_where_sustained_speech_started() -> None:
    frames = [_frame(1, dbfs=-60.0), _frame(2), _frame(3)]

    assert _signals(_AlwaysSpeech(), frames) == [BargeInSignal(sequence=2)]


def test_speech_strategy_ignores_speech_below_the_minimum_duration() -> None:
    frames = [_frame(1), _frame(2, dbfs=-60.0), _frame(3)]

    assert _signals(_AlwaysSpeech(), frames) == []


def test_speech_strategy_does_not_sustain_speech_across_missed_frames() -> None:
    frames = [_frame(1), _frame(3)]

    assert _signals(_AlwaysSpeech(), frames) == []


def test_speech_strategy_never_interrupts_on_the_assistants_own_voice() -> None:
    # Loud, and speech by every measure the detector has - but it is the
    # assistant's own playback leaking through an imperfect canceller.
    frames = [_frame(sequence, echo_confidence=0.8) for sequence in (1, 2, 3, 4)]

    assert _signals(_AlwaysSpeech(), frames) == []


def test_speech_strategy_interrupts_once_the_room_is_no_longer_just_playback() -> None:
    frames = [
        _frame(1, echo_confidence=0.8),
        # The user speaks up, so the playback no longer explains the window.
        _frame(2, echo_confidence=0.2),
        _frame(3, echo_confidence=0.2),
    ]

    assert _signals(_AlwaysSpeech(), frames) == [BargeInSignal(sequence=2)]


def test_speech_strategy_keeps_loud_non_speech_from_interrupting() -> None:
    detector = _NeverSpeech()

    assert _signals(detector, [_frame(1), _frame(2), _frame(3)]) == []
    assert detector.scored_windows == 6


def test_speech_strategy_keeps_silence_away_from_the_detector() -> None:
    detector = _AlwaysSpeech()

    _signals(detector, [_frame(1, dbfs=-80.0)])

    assert detector.scored_windows == 0


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


class _Frames(AudioFrameSource):
    def __init__(self, frames: list[AudioFrame]) -> None:
        self._frames = frames

    @property
    def format(self) -> AudioFormat:
        return _FORMAT

    async def live_frames(self) -> AsyncIterator[AudioFrame]:
        for frame in self._frames:
            yield frame


def _signals(
    detector: VoiceActivityDetector, frames: list[AudioFrame]
) -> list[BargeInSignal]:
    strategy: BargeInStrategy = SpeechBargeIn(
        _Frames(frames),
        detector=detector,
        min_level_dbfs=-40.0,
        min_speech_seconds=0.096,
    )

    async def run() -> list[BargeInSignal]:
        return [signal async for signal in strategy.signals()]

    return asyncio.run(run())


def _frame(
    sequence: int, *, dbfs: float = _LOUD, echo_confidence: float = 0.0
) -> AudioFrame:
    amplitude = round(32_768.0 * 10 ** (dbfs / 20.0))
    pcm = np.full(1_024, amplitude, dtype=np.int16).tobytes()
    return AudioFrame(sequence, pcm, echo_confidence=echo_confidence)
