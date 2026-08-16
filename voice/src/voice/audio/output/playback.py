import asyncio
from typing import Protocol


class AudioPlayback(Protocol):
    """Plays WAV-encoded audio responses."""

    async def play(self, audio: bytes, *, cancel: asyncio.Event | None = None) -> None:
        """Play the given WAV audio and return when playback finishes."""
        ...


class VolumeControl(Protocol):
    """Reads and changes an audio output's volume."""

    async def get_volume(self) -> float:
        """Return the current volume from 0.0 to 1.0."""
        ...

    async def set_volume(self, volume: float) -> None:
        """Set the volume, clamped to 0.0-1.0."""
        ...
