import asyncio
import contextlib
import functools
import logging
import signal
import sys
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

import numpy as np
import pyaudio
from openwakeword.model import Model

from cara.wakeword.views import WAKE_WORD_MODEL, WakeWord

logger = logging.getLogger(__name__)


@dataclass
class AudioConfig:
    chunk: int = 1280
    rate: int = 16000
    channels: int = 1


class WakeWordListener:
    def __init__(
        self,
        on_detection: Callable[[], Awaitable[None]],
        wake_word: WakeWord = WakeWord.HEY_MYCROFT,
        sensitivity: float = 0.5,
        audio_config: AudioConfig | None = None,
    ) -> None:
        if not 0.0 <= sensitivity <= 1.0:
            raise ValueError("Sensitivity must be between 0.0 and 1.0.")

        self._wake_word = wake_word
        self._sensitivity = sensitivity
        self._on_detection = on_detection
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

    async def listen(self) -> None:
        logger.info('Listening for "%s"...', self._wake_word)

        loop = asyncio.get_running_loop()
        if sys.platform != "win32":
            loop.add_signal_handler(signal.SIGINT, self._shutdown)
        else:
            signal.signal(signal.SIGINT, lambda *_: self._shutdown())

        while True:
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
            await self._process_audio(pcm)

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

    async def _process_audio(self, pcm: bytes) -> None:
        audio = np.frombuffer(pcm, dtype=np.int16)
        predictions = self._model.predict(audio)

        if not predictions:
            return

        score = max(predictions.values())
        if score < self._sensitivity:
            return

        logger.info("Wake word detected (score=%.2f) - pausing listener.", score)
        self._stream.stop_stream()

        await self._on_detection()

        self._model.reset()
        self._stream.start_stream()
        logger.info('Listening for "%s"...', self._wake_word)

    def _shutdown(self) -> None:
        logger.info("Shutting down...")
        self._stream.stop_stream()
        self._stream.close()
        self._pa.terminate()
        sys.exit(0)
