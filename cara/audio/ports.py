import asyncio
from abc import ABC, abstractmethod
from enum import StrEnum


class AudioOutput(StrEnum):
    LOCAL = "local"
    SONOS = "sonos"


class SpeechRecorder(ABC):
    """Records a single user utterance into WAV-encoded bytes."""

    @abstractmethod
    async def record_until_silence(
        self,
        *,
        initial_silence_timeout: float | None = None,
    ) -> bytes | None:
        """Record one utterance, optionally timing out before speech begins."""


class AudioPlayback(ABC):
    """Plays WAV-encoded audio."""

    @abstractmethod
    async def play(self, audio: bytes, *, cancel: asyncio.Event | None = None) -> None:
        """Play the given WAV audio and return once playback is finished."""


class AudioOutputStrategy(AudioPlayback):
    """Plays audio through a specific, selectable output implementation."""

    @property
    @abstractmethod
    def output(self) -> AudioOutput:
        """Return the output represented by this strategy."""
