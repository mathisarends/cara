from abc import ABC, abstractmethod


class AudioOutput(ABC):
    """Plays raw signed 16-bit PCM chunks through an audio device."""

    @property
    @abstractmethod
    def is_playing(self) -> bool:
        """Return whether audio is currently buffered or playing."""

    @abstractmethod
    async def start(self, *, sample_rate: int, channels: int) -> None:
        """Open the device for PCM with the given format."""

    @abstractmethod
    async def stop(self) -> None:
        """Stop playback and release resources."""

    @abstractmethod
    async def play_chunk(self, chunk: bytes) -> None:
        """Enqueue a raw signed 16-bit PCM chunk."""

    async def finish_response(self) -> None:  # noqa: B027 - optional output hook
        """Flush the current response after its final chunk."""

    @abstractmethod
    async def clear_buffer(self) -> None:
        """Discard all queued audio immediately."""
