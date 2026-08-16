from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class WakeWordDetection:
    sequence: int
    score: float
    name: str
