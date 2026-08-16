from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AudioFormat:
    sample_rate: int = 16_000
    channels: int = 1
    sample_width: int = 2


@dataclass(frozen=True, slots=True)
class AudioFrame:
    sequence: int
    captured_at: float
    pcm: bytes
