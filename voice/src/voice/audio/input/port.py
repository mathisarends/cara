from abc import ABC, abstractmethod
from collections.abc import AsyncIterator


class AudioInput(ABC):
    """Captures raw signed 16-bit PCM chunks from an audio device."""

    @property
    @abstractmethod
    def sample_rate(self) -> int:
        """Return the number of captured samples per second."""

    @property
    @abstractmethod
    def channels(self) -> int:
        """Return the number of captured audio channels."""

    @property
    @abstractmethod
    def is_active(self) -> bool:
        """Return whether the device is currently capturing."""

    @abstractmethod
    async def start(self) -> None:
        """Open the device and begin capture."""

    @abstractmethod
    async def stop(self) -> None:
        """Stop capture and release resources."""

    @abstractmethod
    def stream_chunks(self) -> AsyncIterator[bytes]:
        """Yield raw signed 16-bit PCM chunks while the input is active."""
