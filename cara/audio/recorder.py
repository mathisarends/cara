import asyncio
import functools
import io
import logging
import threading
import time
import wave
from collections import deque
from dataclasses import dataclass

import numpy as np

from cara.audio.microphone import MicrophoneStream
from cara.audio.ports import SpeechRecorder

logger = logging.getLogger(__name__)

_SAMPLE_WIDTH = 2
_PREROLL_SECONDS = 0.5


@dataclass(frozen=True)
class MicrophoneInputSettings:
    chunk: int = 160
    silence_threshold: int = 500
    silence_seconds: float = 1.2
    min_record_seconds: float = 0.4
    max_record_seconds: float = 12.0


class MicrophoneRecorder(SpeechRecorder):
    """Records one user utterance from a shared microphone stream into a WAV file."""

    def __init__(
        self,
        microphone: MicrophoneStream,
        config: MicrophoneInputSettings | None = None,
    ) -> None:
        self._microphone = microphone
        self.config = config or MicrophoneInputSettings()

    async def record_until_silence(
        self,
        *,
        initial_silence_timeout: float | None = None,
        ready: threading.Event | None = None,
    ) -> bytes | None:
        loop = asyncio.get_running_loop()
        cancelled = threading.Event()
        recording = loop.run_in_executor(
            None,
            functools.partial(
                self._record_until_silence_sync,
                initial_silence_timeout=initial_silence_timeout,
                cancel=cancelled,
                ready=ready,
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
        ready: threading.Event | None = None,
    ) -> bytes | None:
        config = self.config
        mic = self._microphone
        rate = mic.rate

        frames: list[bytes] = []
        preroll: deque[bytes] = deque(maxlen=max(1, int(_PREROLL_SECONDS * rate / config.chunk)))
        started_at = time.monotonic()
        voice_started_at: float | None = None
        silent_chunks = 0
        required_silent_chunks = max(1, int(config.silence_seconds * rate / config.chunk))

        logger.info("Recording user utterance...")
        while True:
            if cancel is not None and cancel.is_set():
                logger.info("Recording cancelled.")
                return None
            pcm = mic.read(config.chunk)

            now = time.monotonic()
            rms = _rms_int16(pcm)

            # Before speech begins, keep only a short pre-roll so the onset of
            # the first word is never clipped; capture starts the instant the
            # microphone crosses the speech threshold - even while the wake
            # earcon is still playing.
            if voice_started_at is None:
                preroll.append(pcm)
                if rms >= config.silence_threshold:
                    voice_started_at = now
                    frames.extend(preroll)
                    preroll.clear()
                elif initial_silence_timeout is not None and now - started_at >= initial_silence_timeout:
                    logger.info("No speech detected within %.1fs.", initial_silence_timeout)
                    return None
                continue

            frames.append(pcm)

            # End-of-utterance silence detection stays suspended until ``ready``,
            # so an overlapping earcon (and its acoustic bleed) can never end the
            # recording before the user has actually finished speaking.
            armed = ready is None or ready.is_set()
            voice_elapsed = now - voice_started_at
            if armed and rms < config.silence_threshold and voice_elapsed >= config.min_record_seconds:
                silent_chunks += 1
            else:
                silent_chunks = 0

            if silent_chunks >= required_silent_chunks:
                break
            if voice_elapsed >= config.max_record_seconds:
                logger.info("Recording reached max duration of %.1fs.", config.max_record_seconds)
                break

        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as wav:
            wav.setnchannels(mic.channels)
            wav.setsampwidth(_SAMPLE_WIDTH)
            wav.setframerate(rate)
            wav.writeframes(b"".join(frames))

        audio = buffer.getvalue()
        logger.info("Recorded utterance (%d bytes).", len(audio))
        return audio


def _rms_int16(pcm: bytes) -> int:
    audio = np.frombuffer(pcm, dtype=np.int16)
    if audio.size == 0:
        return 0
    return int(np.sqrt(np.mean(audio.astype(np.float64) ** 2)))
