import logging
import math

import numpy as np

from voice.echo_cancellation.reference import PlaybackReference

_INT16_PEAK = 32_768.0
_SILENCE_DBFS = -120.0
_EPSILON = 1e-12

logger = logging.getLogger(__name__)


class ReferenceAligner:
    """Finds which known playback samples are present in microphone audio."""

    def __init__(
        self,
        reference: PlaybackReference,
        *,
        window_seconds: float = 0.16,
        interval_seconds: float = 0.08,
        tracking_seconds: float = 0.06,
        filter_headroom_seconds: float = 0.02,
        min_correlation: float = 0.25,
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

    @property
    def is_aligned(self) -> bool:
        return self._next_reference_sample is not None

    def reset(self) -> None:
        self._generation = -1
        self._near_history = np.zeros(0, dtype=np.float64)
        self._samples_since_search = 0
        self._next_reference_sample = None

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

    def _measure(self) -> int | None:
        if self._near_history.size < self._window_samples:
            return None
        if self._samples_since_search < self._interval_samples:
            return None
        self._samples_since_search = 0
        if _level_dbfs(self._near_history) < self._min_level_dbfs:
            return None

        snapshot = self._reference.snapshot()
        reference = _decode(snapshot.pcm)
        search_start = snapshot.first_sample
        if self._next_reference_sample is not None:
            expected = self._next_reference_sample - self._near_history.size
            lower = max(expected - self._tracking_samples, snapshot.first_sample)
            upper = min(
                expected + self._tracking_samples + self._near_history.size,
                snapshot.first_sample + reference.size,
            )
            reference = reference[
                lower - snapshot.first_sample : upper - snapshot.first_sample
            ]
            search_start = lower
        if reference.size < self._near_history.size:
            return None
        if _level_dbfs(reference) < self._min_level_dbfs:
            return None

        step = self._decimation
        lag, correlation = _best_match(reference[::step], self._near_history[::step])
        if correlation < self._min_correlation:
            return None
        # Put the correlated direct path inside the adaptive filter's causal
        # tail. The reference therefore leads the microphone echo slightly.
        measured = search_start + lag * step + self._filter_headroom_samples
        if self.is_aligned:
            logger.debug(
                "AEC reference tracked at sample %d (correlation=%.2f)",
                measured,
                correlation,
            )
        else:
            logger.info(
                "AEC reference acquired (correlation=%.2f)",
                correlation,
            )
        return measured


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
