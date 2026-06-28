import asyncio
import functools
import io
import logging
import time
import wave
from abc import ABC, abstractmethod
from dataclasses import dataclass

import numpy as np
import pyaudio

logger = logging.getLogger(__name__)


class UtteranceRecorder(ABC):
    """Records a single user utterance into WAV-encoded bytes."""

    @abstractmethod
    async def record_until_silence(self, *, initial_silence_timeout: float | None = None) -> bytes | None:
        """Record until the user stops speaking, or return ``None`` if no speech starts."""


class AudioPlayer(ABC):
    """Plays WAV-encoded audio through an output device."""

    @abstractmethod
    async def play(self, audio: bytes, *, cancel: asyncio.Event | None = None) -> None:
        """Play the given WAV audio and return once playback is finished."""


@dataclass(frozen=True)
class MicrophoneRecorderConfig:
    rate: int = 16000
    channels: int = 1
    chunk: int = 1024
    sample_width: int = 2
    silence_threshold: int = 500
    silence_seconds: float = 1.2
    min_record_seconds: float = 0.4
    max_record_seconds: float = 12.0


class MicrophoneRecorder(UtteranceRecorder):
    """Records one user utterance from the default microphone into a WAV file."""

    def __init__(self, config: MicrophoneRecorderConfig | None = None) -> None:
        self.config = config or MicrophoneRecorderConfig()

    async def record_until_silence(self, *, initial_silence_timeout: float | None = None) -> bytes | None:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None,
            functools.partial(
                self._record_until_silence_sync,
                initial_silence_timeout=initial_silence_timeout,
            ),
        )

    def _record_until_silence_sync(self, *, initial_silence_timeout: float | None = None) -> bytes | None:
        config = self.config
        pa = pyaudio.PyAudio()
        stream = pa.open(
            rate=config.rate,
            channels=config.channels,
            format=pyaudio.paInt16,
            input=True,
            frames_per_buffer=config.chunk,
        )
        frames: list[bytes] = []
        started_at = time.monotonic()
        has_voice = False
        silent_chunks = 0
        required_silent_chunks = max(1, int(config.silence_seconds * config.rate / config.chunk))

        logger.info("Recording user utterance...")
        try:
            while True:
                pcm = stream.read(config.chunk, exception_on_overflow=False)
                frames.append(pcm)

                elapsed = time.monotonic() - started_at
                rms = _rms_int16(pcm)
                if not has_voice and rms >= config.silence_threshold:
                    has_voice = True

                if not has_voice and initial_silence_timeout is not None and elapsed >= initial_silence_timeout:
                    logger.info("No speech detected within %.1fs.", initial_silence_timeout)
                    return None

                if has_voice and rms < config.silence_threshold and elapsed >= config.min_record_seconds:
                    silent_chunks += 1
                else:
                    silent_chunks = 0

                if has_voice and silent_chunks >= required_silent_chunks:
                    break
                if elapsed >= config.max_record_seconds:
                    logger.info("Recording reached max duration of %.1fs.", config.max_record_seconds)
                    break
        finally:
            stream.stop_stream()
            stream.close()
            pa.terminate()

        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as wav:
            wav.setnchannels(config.channels)
            wav.setsampwidth(config.sample_width)
            wav.setframerate(config.rate)
            wav.writeframes(b"".join(frames))

        audio = buffer.getvalue()
        logger.info("Recorded utterance (%d bytes).", len(audio))
        return audio


def _rms_int16(pcm: bytes) -> int:
    audio = np.frombuffer(pcm, dtype=np.int16)
    if audio.size == 0:
        return 0
    return int(np.sqrt(np.mean(audio.astype(np.float64) ** 2)))


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
