import asyncio
import functools
import io
import logging
import wave
from abc import ABC, abstractmethod

import pyaudio

logger = logging.getLogger(__name__)


class AudioPlayer(ABC):
    """Plays WAV-encoded audio through an output device."""

    @abstractmethod
    async def play(self, audio: bytes, *, cancel: asyncio.Event | None = None) -> None:
        """Play the given WAV audio and return once playback is finished."""


class WavAudioPlayer(AudioPlayer):
    """Plays WAV audio through the default output device."""

    async def play(self, audio: bytes, *, cancel: asyncio.Event | None = None) -> None:
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, functools.partial(self._play_sync, audio, cancel=cancel))

    def _play_sync(self, audio: bytes, *, cancel: asyncio.Event | None = None) -> None:
        pa = pyaudio.PyAudio()
        try:
            with wave.open(io.BytesIO(audio), "rb") as wav:
                stream = pa.open(
                    format=pa.get_format_from_width(wav.getsampwidth()),
                    channels=wav.getnchannels(),
                    rate=wav.getframerate(),
                    output=True,
                )
                try:
                    while chunk := wav.readframes(1024):
                        if cancel is not None and cancel.is_set():
                            logger.info("Audio playback cancelled.")
                            break
                        stream.write(chunk)
                finally:
                    stream.stop_stream()
                    stream.close()
        finally:
            pa.terminate()
