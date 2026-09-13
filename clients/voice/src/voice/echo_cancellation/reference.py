from dataclasses import dataclass

_BYTES_PER_SAMPLE = 2


@dataclass(frozen=True, slots=True)
class ReferenceSnapshot:
    generation: int
    first_sample: int
    pcm: bytes


class PlaybackReference:
    """Retains the PCM sent to one playback, indexed by sample position."""

    def __init__(self, sample_rate: int = 24_000, *, history_seconds: float = 8.0):
        if sample_rate <= 0:
            raise ValueError("sample_rate must be positive")
        if history_seconds <= 0:
            raise ValueError("history_seconds must be positive")
        self._sample_rate = sample_rate
        self._capacity = round(history_seconds * sample_rate)
        self._generation = 0
        self._first_sample = 0
        self._pcm = bytearray()

    @property
    def sample_rate(self) -> int:
        return self._sample_rate

    @property
    def generation(self) -> int:
        return self._generation

    def start_playback(self) -> None:
        self._generation += 1
        self._first_sample = 0
        self._pcm.clear()

    def write(self, chunk: bytes) -> None:
        if len(chunk) % _BYTES_PER_SAMPLE:
            raise ValueError("Reference PCM must contain complete samples.")
        self._pcm.extend(chunk)
        excess = len(self._pcm) // _BYTES_PER_SAMPLE - self._capacity
        if excess <= 0:
            return
        del self._pcm[: excess * _BYTES_PER_SAMPLE]
        self._first_sample += excess

    def read(self, start_sample: int, sample_count: int) -> bytes:
        if sample_count < 0:
            raise ValueError("sample_count must not be negative")
        result = bytearray(sample_count * _BYTES_PER_SAMPLE)
        source_start = max(start_sample, self._first_sample)
        source_end = min(
            start_sample + sample_count,
            self._first_sample + len(self._pcm) // _BYTES_PER_SAMPLE,
        )
        if source_end <= source_start:
            return bytes(result)

        source_offset = source_start - self._first_sample
        destination_offset = source_start - start_sample
        copied = source_end - source_start
        result[
            destination_offset * _BYTES_PER_SAMPLE : (destination_offset + copied)
            * _BYTES_PER_SAMPLE
        ] = self._pcm[
            source_offset * _BYTES_PER_SAMPLE : (source_offset + copied)
            * _BYTES_PER_SAMPLE
        ]
        return bytes(result)

    def snapshot(self) -> ReferenceSnapshot:
        return ReferenceSnapshot(
            generation=self._generation,
            first_sample=self._first_sample,
            pcm=bytes(self._pcm),
        )
