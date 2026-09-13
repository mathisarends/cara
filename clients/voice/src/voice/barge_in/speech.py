import math
from collections.abc import AsyncIterator

import numpy as np

from voice.barge_in.port import (
    BargeInContext,
    BargeInSignal,
    BargeInStrategy,
    PendingSignal,
)
from voice.echo_cancellation import EchoPresence
from voice.events import UserAudioChunk
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

        self._detector = detector or SileroVoiceActivityDetector()
        self._min_level_dbfs = min_level_dbfs
        self._min_speech_probability = min_speech_probability
        self._min_speech_seconds = min_speech_seconds
        self._max_echo_confidence = max_echo_confidence
        self._echo_presence: EchoPresence | None = None
        self._samples_required = 0
        self._pending = PendingSignal()
        self._buffer = np.zeros(0, dtype=np.int16)
        self._speech_start: int | None = None
        self._voiced_samples = 0

    def set_context(self, context: BargeInContext) -> None:
        audio_format = context.audio_format
        if audio_format.sample_rate != self._detector.sample_rate:
            raise ValueError(
                f"Speech barge-in requires {self._detector.sample_rate} Hz audio."
            )
        if audio_format.channels != 1:
            raise ValueError("Speech barge-in requires mono audio.")

        self._samples_required = math.ceil(
            self._min_speech_seconds * audio_format.sample_rate
        )
        self._echo_presence = context.echo_presence
        context.event_bus.on(UserAudioChunk, self._on_audio_chunk)

    def signals(self) -> AsyncIterator[BargeInSignal]:
        return self._pending.stream()

    async def _on_audio_chunk(self, event: UserAudioChunk) -> None:
        self._buffer = np.concatenate(
            (self._buffer, np.frombuffer(event.chunk, dtype=np.int16))
        )
        window_samples = self._detector.window_samples
        while self._buffer.size >= window_samples:
            window = self._buffer[:window_samples]
            self._buffer = self._buffer[window_samples:]
            self._score_window(window, event.sequence)

    def _score_window(self, window: np.ndarray, sequence: int) -> None:
        if self._hears_own_playback():
            # Whatever the detector would make of this window, the assistant
            # is not allowed to take its own voice for an interruption.
            self._end_speech()
            return
        if not self._is_speech(window):
            self._end_speech()
            return

        if self._speech_start is None:
            self._speech_start = sequence
        self._voiced_samples += window.size
        if self._voiced_samples < self._samples_required:
            return

        speech_start = self._speech_start
        self._end_speech()
        self._pending.put(speech_start)

    def _hears_own_playback(self) -> bool:
        if self._echo_presence is None:
            return False
        return self._echo_presence.echo_confidence >= self._max_echo_confidence

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
