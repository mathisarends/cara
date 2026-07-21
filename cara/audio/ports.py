import asyncio
import threading
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
        ready: threading.Event | None = None,
    ) -> bytes | None:
        """Record one utterance, optionally timing out before speech begins.

        Capture begins immediately, so speech spoken right after the wake word -
        even over a still-playing earcon - is kept. While ``ready`` is provided
        and unset, end-of-utterance silence detection is suspended so the earcon
        cannot end the recording before the user has finished speaking.
        """


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

    @abstractmethod
    async def get_volume(self) -> float:
        """Return the current playback volume, from 0.0 (silent) to 1.0 (full)."""

    @abstractmethod
    async def set_volume(self, volume: float) -> None:
        """Set the playback volume, clamped to 0.0-1.0."""
