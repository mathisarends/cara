import asyncio
import threading
from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from enum import StrEnum
from typing import Protocol


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
        on_speech_started: Callable[[], Awaitable[None]] | None = None,
    ) -> bytes | None:
        """Record one utterance, optionally timing out before speech begins.

        Capture begins immediately, so speech spoken right after the wake word -
        even over a still-playing earcon - is kept. While ``ready`` is provided
        and unset, end-of-utterance silence detection is suspended so the earcon
        cannot end the recording before the user has finished speaking. The
        optional handler runs once, when voice activity is first detected.
        """


class TurnDetector(ABC):
    """Decides whether the current spoken turn is semantically complete."""

    @property
    @abstractmethod
    def sample_rate(self) -> int:
        """Return the required PCM sample rate."""

    @abstractmethod
    def is_complete(self, utterance: bytes) -> bool:
        """Return whether the mono int16 PCM utterance is a complete turn."""


class AudioPlayback(Protocol):
    """Plays WAV-encoded audio."""

    async def play(self, audio: bytes, *, cancel: asyncio.Event | None = None) -> None:
        """Play the given WAV audio and return once playback is finished."""
        ...


class VolumeControl(Protocol):
    """Reads and changes an audio destination's volume."""

    async def get_volume(self) -> float:
        """Return the current volume, from 0.0 (silent) to 1.0 (full)."""
        ...

    async def set_volume(self, volume: float) -> None:
        """Set the volume, clamped to 0.0-1.0."""
        ...


class AudioSink(AudioPlayback, Protocol):
    """Plays audio through a specific, selectable destination."""

    @property
    def output(self) -> AudioOutput:
        """Return the output represented by this sink."""
        ...


class AudioController(AudioSink, VolumeControl, Protocol):
    """Controls playback and volume for one selectable audio destination."""
