import asyncio
from abc import ABC, abstractmethod


class SpeechRecorder(ABC):
    """Records a single user utterance into WAV-encoded bytes."""

    @abstractmethod
    async def record_until_silence(self, *, initial_silence_timeout: float | None = None) -> bytes | None:
        """Record until the user stops speaking, or return ``None`` if no speech starts."""


class AudioPlayer(ABC):
    """Plays WAV-encoded audio through an output device."""

    @abstractmethod
    async def play(self, audio: bytes, *, cancel: asyncio.Event | None = None) -> None:
        """Play the given WAV audio and return once playback is finished."""
