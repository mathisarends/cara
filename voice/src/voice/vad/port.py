from abc import ABC, abstractmethod


class VoiceActivityDetector(ABC):
    """Scores fixed-size PCM windows for the presence of human speech."""

    @property
    @abstractmethod
    def sample_rate(self) -> int:
        """Return the sample rate the scored windows must be captured at."""

    @property
    @abstractmethod
    def window_samples(self) -> int:
        """Return the number of mono samples one scored window carries."""

    @abstractmethod
    def speech_probability(self, window: bytes) -> float:
        """Return how likely the signed 16-bit PCM window carries speech."""

    @abstractmethod
    def reset(self) -> None:
        """Drop the context kept from previously scored windows."""
