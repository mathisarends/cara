import math
from collections.abc import AsyncIterator

import numpy as np

from voice.audio import AudioFrame, AudioFrameSource
from voice.barge_in.port import BargeInSignal, BargeInStrategy
from voice.vad import SileroVoiceActivityDetector, VoiceActivityDetector

_SILENCE_DBFS = -120.0
_FULL_SCALE = 32_768.0


class SpeechBargeIn(BargeInStrategy):
    """Interrupts once the user speaks over the assistant for long enough.

    Frames arrive echo-cancelled, but only the room decides how well that
    worked, so leaked playback can still look like speech. A run of voiced
    windows therefore only counts while the assistant's own sound is not
    what the microphone is hearing.
    """

    def __init__(
        self,
        frames: AudioFrameSource,
        *,
        detector: VoiceActivityDetector | None = None,
        min_level_dbfs: float = -45.0,
        min_speech_probability: float = 0.6,
        min_speech_seconds: float = 0.35,
        max_echo_confidence: float = 0.5,
    ) -> None:
        if min_level_dbfs > 0.0:
            raise ValueError("min_level_dbfs must not exceed full scale")
        if not 0.0 < min_speech_probability <= 1.0:
            raise ValueError("min_speech_probability must be within (0, 1]")
        if min_speech_seconds <= 0:
            raise ValueError("min_speech_seconds must be positive")
        if not 0.0 < max_echo_confidence <= 1.0:
            raise ValueError("max_echo_confidence must be within (0, 1]")
        detector = detector or SileroVoiceActivityDetector()
        audio_format = frames.format
        if audio_format.sample_rate != detector.sample_rate:
            raise ValueError(
                f"Speech barge-in requires {detector.sample_rate} Hz audio."
            )
        if audio_format.channels != 1:
            raise ValueError("Speech barge-in requires mono audio.")

        self._frames = frames
        self._detector = detector
        self._min_level_dbfs = min_level_dbfs
        self._min_speech_probability = min_speech_probability
        self._samples_required = math.ceil(
            min_speech_seconds * audio_format.sample_rate
        )
        self._max_echo_confidence = max_echo_confidence
        self._buffer = np.zeros(0, dtype=np.int16)
        self._speech_start: int | None = None
        self._voiced_samples = 0

    async def signals(self) -> AsyncIterator[BargeInSignal]:
        previous_sequence: int | None = None
        async for frame in self._frames.live_frames():
            if (
                previous_sequence is not None
                and frame.sequence != previous_sequence + 1
            ):
                # Speech cannot be sustained across audio this strategy missed.
                self._buffer = np.zeros(0, dtype=np.int16)
                self._end_speech()
            previous_sequence = frame.sequence
            speech_start = self._score_frame(frame)
            if speech_start is not None:
                yield BargeInSignal(sequence=speech_start)

    def _score_frame(self, frame: AudioFrame) -> int | None:
        self._buffer = np.concatenate(
            (self._buffer, np.frombuffer(frame.pcm, dtype=np.int16))
        )
        window_samples = self._detector.window_samples
        speech_start: int | None = None
        while self._buffer.size >= window_samples:
            window = self._buffer[:window_samples]
            self._buffer = self._buffer[window_samples:]
            started = self._score_window(window, frame)
            if started is not None and speech_start is None:
                speech_start = started
        return speech_start

    def _score_window(self, window: np.ndarray, frame: AudioFrame) -> int | None:
        if frame.echo_confidence >= self._max_echo_confidence:
            # Whatever the detector would make of this window, the assistant
            # is not allowed to take its own voice for an interruption.
            self._end_speech()
            return None
        if not self._is_speech(window):
            self._end_speech()
            return None

        if self._speech_start is None:
            self._speech_start = frame.sequence
        self._voiced_samples += window.size
        if self._voiced_samples < self._samples_required:
            return None

        speech_start = self._speech_start
        self._end_speech()
        return speech_start

    def _is_speech(self, window: np.ndarray) -> bool:
        if _level_dbfs(window) < self._min_level_dbfs:
            return False
        probability = self._detector.speech_probability(window.tobytes())
        return probability >= self._min_speech_probability

    def _end_speech(self) -> None:
        if self._speech_start is None:
            return
        self._speech_start = None
        self._voiced_samples = 0
        # Windows below the gate never reach the detector, so its context
        # would otherwise carry across the gap.
        self._detector.reset()


def _level_dbfs(samples: np.ndarray) -> float:
    if samples.size == 0:
        return _SILENCE_DBFS
    normalized = samples.astype(np.float64) / _FULL_SCALE
    rms = float(np.sqrt(np.mean(np.square(normalized))))
    if rms <= 0.0:
        return _SILENCE_DBFS
    return 20.0 * math.log10(rms)
