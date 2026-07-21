import asyncio
import contextlib
import functools
import logging
import signal
import sys
from collections.abc import AsyncIterator
from dataclasses import dataclass

import numpy as np
import pyaudio
from openwakeword.model import Model

from cara.wakeword.ports import WakeWordDetectionSource
from cara.wakeword.views import WAKE_WORD_MODEL, WakeWord

logger = logging.getLogger(__name__)


@dataclass
class AudioConfig:
    chunk: int = 1280
    rate: int = 16000
    channels: int = 1


class WakeWordListener(WakeWordDetectionSource):
    def __init__(
        self,
        wake_word: WakeWord = WakeWord.HEY_MYCROFT,
        sensitivity: float = 0.5,
        audio_config: AudioConfig | None = None,
    ) -> None:
        if not 0.0 <= sensitivity <= 1.0:
            raise ValueError("Sensitivity must be between 0.0 and 1.0.")

        self._wake_word = wake_word
        self._sensitivity = sensitivity
        self._audio_config = audio_config or AudioConfig()
        self._model = Model(
            wakeword_models=[WAKE_WORD_MODEL[wake_word]],
            inference_framework="onnx",
        )
        self._pa = pyaudio.PyAudio()
        self._stream = self._pa.open(
            rate=self._audio_config.rate,
            channels=self._audio_config.channels,
            format=pyaudio.paInt16,
            input=True,
            frames_per_buffer=self._audio_config.chunk,
        )
        self._closed = False

    async def detections(self) -> AsyncIterator[float]:
        """Yield the detection score once per wake-word detection.

        The microphone stream is paused while the consumer handles a detection
        and resumed when it requests the next one, so the recorder can reuse the
        microphone during a session.
        """
        logger.info('Listening for "%s"...', self._wake_word)

        loop = asyncio.get_running_loop()
        if sys.platform != "win32":
            loop.add_signal_handler(signal.SIGINT, self._shutdown)
        else:
            signal.signal(signal.SIGINT, lambda *_: self._shutdown())

        while True:
            score = await self.detect_once()
            if score is None:
                continue
            yield score
            logger.info('Listening for "%s"...', self._wake_word)

    async def detect_once(self, *, cancel: asyncio.Event | None = None) -> float | None:
        """Listen until the wake word is detected or cancellation is requested."""
        if self._closed:
            raise RuntimeError("Wake-word listener is closed.")

        self._model.reset()
        if self._stream.is_stopped():
            self._stream.start_stream()

        loop = asyncio.get_running_loop()
        while cancel is None or not cancel.is_set():
            try:
                pcm = await loop.run_in_executor(
                    None,
                    functools.partial(
                        self._stream.read,
                        self._audio_config.chunk,
                        exception_on_overflow=False,
                    ),
                )
            except OSError as err:
                if err.errno in (-9988, -9983):
                    logger.warning("Audio stream closed - reopening...")
                    self._reopen_stream()
                    continue
                raise

            if cancel is not None and cancel.is_set():
                break

            score = self._detect(pcm)
            if score is None:
                continue

            logger.info("Wake word detected (score=%.2f) - pausing listener.", score)
            self._stream.stop_stream()
            return score

        self._stream.stop_stream()
        return None

    def close(self) -> None:
        if self._closed:
            return
        if self._stream.is_active():
            self._stream.stop_stream()
        self._stream.close()
        self._pa.terminate()
        self._closed = True

    def _reopen_stream(self) -> None:
        with contextlib.suppress(Exception):
            self._stream.close()
        self._stream = self._pa.open(
            rate=self._audio_config.rate,
            channels=self._audio_config.channels,
            format=pyaudio.paInt16,
            input=True,
            frames_per_buffer=self._audio_config.chunk,
        )

    def _detect(self, pcm: bytes) -> float | None:
        audio = np.frombuffer(pcm, dtype=np.int16)
        predictions = self._model.predict(audio)

        if not predictions:
            return None

        score = max(predictions.values())
        if score < self._sensitivity:
            return None

        return score

    def _shutdown(self) -> None:
        logger.info("Shutting down...")
        self.close()
        sys.exit(0)
