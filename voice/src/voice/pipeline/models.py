from dataclasses import dataclass
from enum import StrEnum


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


@dataclass(frozen=True, slots=True)
class WakeWordDetection:
    sequence: int
    score: float
    name: str


class TurnState(StrEnum):
    STARTING = "starting"
    ARMED = "armed"
    LISTENING = "listening"
    THINKING = "thinking"
    SPEAKING = "speaking"
