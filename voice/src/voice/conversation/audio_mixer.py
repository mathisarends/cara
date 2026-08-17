import time
import wave
from collections.abc import Callable
from pathlib import Path

import numpy as np

_SAMPLE_WIDTH = 2


class ConversationAudioMixer:
    """Mixes timestamped mono PCM from a user and assistant into one WAV file."""

    def __init__(
        self,
        path: str | Path,
        *,
        user_sample_rate: int = 16_000,
        assistant_sample_rate: int = 24_000,
        output_sample_rate: int = 24_000,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if min(user_sample_rate, assistant_sample_rate, output_sample_rate) <= 0:
            raise ValueError("sample rates must be positive")
        self._path = Path(path)
        self._user_sample_rate = user_sample_rate
        self._assistant_sample_rate = assistant_sample_rate
        self._output_sample_rate = output_sample_rate
        self._clock = clock
        self._started_at: float | None = None
        self._user_chunks: list[tuple[float, bytes]] = []
        self._assistant_chunks: list[tuple[float, bytes]] = []
        self._duration = 0.0

    @property
    def path(self) -> Path:
        return self._path

    def feed_user(self, data: bytes) -> None:
        _validate_pcm(data)
        if data:
            self._user_chunks.append((self._now(), data))

    def feed_assistant(self, data: bytes) -> None:
        _validate_pcm(data)
        if data:
            self._assistant_chunks.append((self._now(), data))

    def finalize(self) -> None:
        self._duration = max(
            _track_end(self._user_chunks, self._user_sample_rate),
            _track_end(self._assistant_chunks, self._assistant_sample_rate),
        )

    def save(self) -> None:
        self.finalize()
        total_samples = round(self._duration * self._output_sample_rate)
        if total_samples == 0:
            return

        user = _render_track(
            self._user_chunks,
            source_sample_rate=self._user_sample_rate,
            output_sample_rate=self._output_sample_rate,
            total_samples=total_samples,
        )
        assistant = _render_track(
            self._assistant_chunks,
            source_sample_rate=self._assistant_sample_rate,
            output_sample_rate=self._output_sample_rate,
            total_samples=total_samples,
        )
        mixed = np.clip(
            user.astype(np.int32) + assistant.astype(np.int32),
            np.iinfo(np.int16).min,
            np.iinfo(np.int16).max,
        ).astype("<i2")

        self._path.parent.mkdir(parents=True, exist_ok=True)
        with wave.open(str(self._path), "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(_SAMPLE_WIDTH)
            wav_file.setframerate(self._output_sample_rate)
            wav_file.writeframes(mixed.tobytes())

    def _now(self) -> float:
        now = self._clock()
        if self._started_at is None:
            self._started_at = now
        return now - self._started_at


def _validate_pcm(data: bytes) -> None:
    if len(data) % _SAMPLE_WIDTH:
        raise ValueError("PCM data must contain complete 16-bit samples")


def _track_end(chunks: list[tuple[float, bytes]], sample_rate: int) -> float:
    if not chunks:
        return 0.0
    timestamp, data = chunks[-1]
    return timestamp + len(data) / _SAMPLE_WIDTH / sample_rate


def _render_track(
    chunks: list[tuple[float, bytes]],
    *,
    source_sample_rate: int,
    output_sample_rate: int,
    total_samples: int,
) -> np.ndarray:
    track = np.zeros(total_samples, dtype="<i2")
    for timestamp, data in chunks:
        samples = np.frombuffer(data, dtype="<i2")
        rendered = _resample(samples, source_sample_rate, output_sample_rate)
        offset = round(timestamp * output_sample_rate)
        usable = rendered[: max(total_samples - offset, 0)]
        if usable.size:
            track[offset : offset + usable.size] = usable
    return track


def _resample(
    samples: np.ndarray, source_sample_rate: int, output_sample_rate: int
) -> np.ndarray:
    if source_sample_rate == output_sample_rate or samples.size == 0:
        return samples
    output_size = round(samples.size * output_sample_rate / source_sample_rate)
    source_positions = np.arange(output_size) * source_sample_rate / output_sample_rate
    return np.interp(
        source_positions,
        np.arange(samples.size),
        samples,
    ).astype("<i2")
