from abc import ABC, abstractmethod


class VoiceActivityDetector(ABC):
    """Classifies fixed-size, mono PCM frames as speech or non-speech."""

    @property
    @abstractmethod
    def sample_rate(self) -> int:
        """Return the required PCM sample rate."""

    @property
    @abstractmethod
    def frame_samples(self) -> int:
        """Return the required number of samples per input frame."""

    @abstractmethod
    def reset(self) -> None:
        """Reset streaming state before recording a new utterance."""

    @abstractmethod
    def is_speech(self, frame: bytes) -> bool:
        """Return whether one mono int16 PCM frame contains speech."""
