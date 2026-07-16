import asyncio
from abc import ABC, abstractmethod


class SpeechRecorder(ABC):
    """Records a single user utterance into WAV-encoded bytes."""

    @abstractmethod
    async def record_until_silence(
        self,
        *,
        initial_silence_timeout: float | None = None,
        speech_started: asyncio.Event | None = None,
        cancel: asyncio.Event | None = None,
    ) -> bytes | None:
        """Record one utterance, optionally signalling its start or stopping early."""


class AudioPlayer(ABC):
    """Plays WAV-encoded audio through an output device."""

    @abstractmethod
    async def play(self, audio: bytes, *, cancel: asyncio.Event | None = None) -> None:
        """Play the given WAV audio and return once playback is finished."""


class EchoCanceller(ABC):
    """Cancels speaker audio from captured 16-bit PCM microphone frames."""

    @property
    @abstractmethod
    def sample_rate(self) -> int: ...

    @property
    @abstractmethod
    def channels(self) -> int: ...

    @abstractmethod
    def analyze_render(
        self,
        pcm: bytes,
        *,
        sample_rate: int,
        channels: int,
        sample_width: int,
    ) -> None: ...

    @abstractmethod
    def process_capture(self, pcm: bytes) -> bytes: ...
