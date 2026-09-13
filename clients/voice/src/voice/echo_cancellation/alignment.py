import logging
import math

import numpy as np

from voice.echo_cancellation.ports import EchoPresence
from voice.echo_cancellation.reference import PlaybackReference

_INT16_PEAK = 32_768.0
_SILENCE_DBFS = -120.0
_EPSILON = 1e-12

logger = logging.getLogger(__name__)


class ReferenceAligner(EchoPresence):
    """Finds which known playback samples are present in microphone audio."""

    def __init__(
        self,
        reference: PlaybackReference,
        *,
        window_seconds: float = 0.16,
        interval_seconds: float = 0.08,
        tracking_seconds: float = 0.06,
        filter_headroom_seconds: float = 0.02,
        min_correlation: float = 0.5,
        min_level_dbfs: float = -50.0,
        analysis_sample_rate: int = 8_000,
    ) -> None:
        sample_rate = reference.sample_rate
        if window_seconds <= 0:
            raise ValueError("window_seconds must be positive")
        if interval_seconds <= 0:
            raise ValueError("interval_seconds must be positive")
        if tracking_seconds < 0:
            raise ValueError("tracking_seconds must not be negative")
        if filter_headroom_seconds < 0:
            raise ValueError("filter_headroom_seconds must not be negative")
        if not 0 < min_correlation <= 1:
            raise ValueError("min_correlation must be within (0, 1]")
        if analysis_sample_rate <= 0 or sample_rate % analysis_sample_rate:
            raise ValueError(
                "analysis_sample_rate must divide the reference sample rate"
            )

        self._reference = reference
        self._window_samples = round(window_seconds * sample_rate)
        self._interval_samples = round(interval_seconds * sample_rate)
        self._tracking_samples = round(tracking_seconds * sample_rate)
        self._filter_headroom_samples = round(filter_headroom_seconds * sample_rate)
        self._min_correlation = min_correlation
        self._min_level_dbfs = min_level_dbfs
        self._decimation = sample_rate // analysis_sample_rate
        self._generation = -1
        self._near_history = np.zeros(0, dtype=np.float64)
        self._samples_since_search = 0
        self._next_reference_sample: int | None = None
        self._echo_confidence = 0.0

    @property
    def is_aligned(self) -> bool:
        return self._next_reference_sample is not None

    @property
    def echo_confidence(self) -> float:
        """How much of the recent microphone audio is our own playback, in 0..1.

        The normalized correlation peak between the microphone window and the
        reference. Near 1 the window is almost purely echo; the more unrelated
        sound the room adds, the further it falls. It stays meaningful whether
        or not the filter is aligned, so callers can judge captured audio
        without depending on cancellation having converged.
        """
        return self._echo_confidence

    def reset(self) -> None:
        self._reset_for(-1)

    def read(self, near_end: bytes) -> bytes:
        near = _decode(near_end)
        generation = self._reference.generation
        if generation != self._generation:
            self._reset_for(generation)

        predicted_start = self._next_reference_sample
        if predicted_start is not None:
            self._next_reference_sample = predicted_start + near.size

        self._near_history = np.concatenate((self._near_history, near))[
            -self._window_samples :
        ]
        self._samples_since_search += near.size
        measured_start = self._measure()
        if measured_start is not None:
            current_start = measured_start + self._near_history.size - near.size
            self._next_reference_sample = measured_start + self._near_history.size
        else:
            current_start = predicted_start

        if current_start is None:
            return bytes(len(near_end))
        return self._reference.read(current_start, near.size)

    def _reset_for(self, generation: int) -> None:
        self._generation = generation
        self._near_history = np.zeros(0, dtype=np.float64)
        self._samples_since_search = 0
        self._next_reference_sample = None
        self._echo_confidence = 0.0

    def _measure(self) -> int | None:
        if self._near_history.size < self._window_samples:
            return None
        if self._samples_since_search < self._interval_samples:
            return None
        self._samples_since_search = 0
        self._echo_confidence = 0.0
        if _level_dbfs(self._near_history) < self._min_level_dbfs:
            return None

        snapshot = self._reference.snapshot()
        reference = _decode(snapshot.pcm)
        if _level_dbfs(reference) < self._min_level_dbfs:
            return None

        match = self._search(reference, snapshot.first_sample)
        if match is None:
            return None

        was_aligned = self.is_aligned
        start, self._echo_confidence = match
        if self._echo_confidence < self._min_correlation:
            return None
        # Put the correlated direct path inside the adaptive filter's causal
        # tail. The reference therefore leads the microphone echo slightly.
        measured = start + self._filter_headroom_samples
        if was_aligned:
            logger.debug(
                "AEC reference tracked at sample %d (correlation=%.2f)",
                measured,
                self._echo_confidence,
            )
        else:
            logger.info(
                "AEC reference acquired (correlation=%.2f)",
                self._echo_confidence,
            )
        return measured

    def _search(
        self, reference: np.ndarray, first_sample: int
    ) -> tuple[int, float] | None:
        """Find where the near-end window sits in the reference.

        A held lock wins as long as it still matches, so tracking stays
        continuous. Otherwise the whole history is searched again and the
        lock moves to wherever the playback actually turned up: the tracking
        window only guesses at playback latency, so a lock that guessed
        wrong corrects itself rather than having to be given up.
        """
        tracked = self._tracked_bounds(reference.size, first_sample)
        if tracked is not None:
            lower, upper = tracked
            match = _locate(
                reference[lower - first_sample : upper - first_sample],
                self._near_history,
                self._decimation,
                lower,
            )
            if match is not None and match[1] >= self._min_correlation:
                return match
        return _locate(reference, self._near_history, self._decimation, first_sample)

    def _tracked_bounds(
        self, reference_size: int, first_sample: int
    ) -> tuple[int, int] | None:
        if self._next_reference_sample is None:
            return None
        expected = self._next_reference_sample - self._near_history.size
        lower = max(expected - self._tracking_samples, first_sample)
        upper = min(
            expected + self._tracking_samples + self._near_history.size,
            first_sample + reference_size,
        )
        return (lower, upper) if upper > lower else None


def _locate(
    reference: np.ndarray,
    near: np.ndarray,
    decimation: int,
    first_sample: int,
) -> tuple[int, float] | None:
    if reference.size < near.size:
        return None
    lag, correlation = _best_match(reference[::decimation], near[::decimation])
    return first_sample + lag * decimation, correlation


def _best_match(reference: np.ndarray, near: np.ndarray) -> tuple[int, float]:
    reference = reference - np.mean(reference)
    near = near - np.mean(near)
    positions = reference.size - near.size + 1
    size = 1 << (reference.size + near.size - 1).bit_length()
    spectrum = np.fft.rfft(reference, size) * np.conj(np.fft.rfft(near, size))
    correlation = np.fft.irfft(spectrum, size)[:positions]
    scale = np.sqrt(_sliding_energy(reference, near.size) * (near @ near)) + _EPSILON
    normalized = np.abs(correlation / scale)
    lag = int(np.argmax(normalized))
    return lag, float(normalized[lag])


def _sliding_energy(samples: np.ndarray, width: int) -> np.ndarray:
    cumulative = np.concatenate(([0.0], np.cumsum(np.square(samples))))
    return cumulative[width:] - cumulative[:-width]


def _decode(pcm: bytes) -> np.ndarray:
    return np.frombuffer(pcm, dtype="<i2").astype(np.float64) / _INT16_PEAK


def _level_dbfs(samples: np.ndarray) -> float:
    if samples.size == 0:
        return _SILENCE_DBFS
    rms = float(np.sqrt(np.mean(np.square(samples))))
    if rms <= 0:
        return _SILENCE_DBFS
    return 20 * math.log10(rms)
