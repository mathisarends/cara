import asyncio
from typing import Protocol


class AudioPlayback(Protocol):
    """Plays WAV audio and controls the output lifecycle."""

    async def play(self, audio: bytes, *, cancel: asyncio.Event | None = None) -> None:
        """Play the given WAV audio and return when playback finishes."""
        ...

    async def stop(self) -> None:
        """Stop playback and release the audio output."""
        ...
