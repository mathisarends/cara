import asyncio
import functools
import io
import logging
import threading
import time
import wave
from dataclasses import dataclass

import numpy as np
import pyaudio

from cara.audio.ports import SpeechRecorder

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class MicrophoneInputSettings:
    rate: int = 16000
    channels: int = 1
    chunk: int = 160
    sample_width: int = 2
    silence_threshold: int = 500
    silence_seconds: float = 1.2
    min_record_seconds: float = 0.4
    max_record_seconds: float = 12.0


class MicrophoneRecorder(SpeechRecorder):
    """Records one user utterance from the default microphone into a WAV file."""

    def __init__(self, config: MicrophoneInputSettings | None = None) -> None:
        self.config = config or MicrophoneInputSettings()

    async def record_until_silence(
        self,
        *,
        initial_silence_timeout: float | None = None,
    ) -> bytes | None:
        loop = asyncio.get_running_loop()
        cancelled = threading.Event()
        recording = loop.run_in_executor(
            None,
            functools.partial(
                self._record_until_silence_sync,
                initial_silence_timeout=initial_silence_timeout,
                cancel=cancelled,
            ),
        )
        try:
            return await asyncio.shield(recording)
        except asyncio.CancelledError:
            cancelled.set()
            await asyncio.shield(recording)
            raise

    def _record_until_silence_sync(
        self,
        *,
        initial_silence_timeout: float | None = None,
        cancel: threading.Event | None = None,
    ) -> bytes | None:
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
        voice_started_at: float | None = None
        silent_chunks = 0
        required_silent_chunks = max(1, int(config.silence_seconds * config.rate / config.chunk))

        logger.info("Recording user utterance...")
        try:
            while True:
                if cancel is not None and cancel.is_set():
                    logger.info("Recording cancelled.")
                    return None
                pcm = stream.read(config.chunk, exception_on_overflow=False)

                elapsed = time.monotonic() - started_at
                rms = _rms_int16(pcm)
                if voice_started_at is None and rms >= config.silence_threshold:
                    voice_started_at = time.monotonic()

                if (
                    voice_started_at is None
                    and initial_silence_timeout is not None
                    and elapsed >= initial_silence_timeout
                ):
                    logger.info("No speech detected within %.1fs.", initial_silence_timeout)
                    return None

                if voice_started_at is None:
                    continue

                frames.append(pcm)
                voice_elapsed = time.monotonic() - voice_started_at
                if rms < config.silence_threshold and voice_elapsed >= config.min_record_seconds:
                    silent_chunks += 1
                else:
                    silent_chunks = 0

                if silent_chunks >= required_silent_chunks:
                    break
                if voice_elapsed >= config.max_record_seconds:
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
