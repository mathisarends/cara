import asyncio
import logging
import signal
import sys
from collections.abc import AsyncIterator

import numpy as np
from openwakeword.model import Model

from cara.audio import MicrophoneStream
from cara.wakeword.ports import WakeWordDetectionSource
from cara.wakeword.views import WAKE_WORD_MODEL, WakeWord

logger = logging.getLogger(__name__)

_PREDICTION_CHUNK = 1280


class WakeWordListener(WakeWordDetectionSource):
    def __init__(
        self,
        microphone: MicrophoneStream,
        *,
        wake_word: WakeWord = WakeWord.HEY_MYCROFT,
        sensitivity: float = 0.5,
    ) -> None:
        if not 0.0 <= sensitivity <= 1.0:
            raise ValueError("Sensitivity must be between 0.0 and 1.0.")

        self._microphone = microphone
        self._wake_word = wake_word
        self._sensitivity = sensitivity
        self._model = Model(
            wakeword_models=[WAKE_WORD_MODEL[wake_word]],
            inference_framework="onnx",
        )

    async def detections(self) -> AsyncIterator[float]:
        """Yield the detection score once per wake-word detection.

        The microphone stream is shared with the recorder, so detection simply
        stops reading while a detection is handled and resumes afterwards; the
        capture itself never pauses.
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
        self._model.reset()
        loop = asyncio.get_running_loop()
        while cancel is None or not cancel.is_set():
            pcm = await loop.run_in_executor(None, self._microphone.read, _PREDICTION_CHUNK)

            if cancel is not None and cancel.is_set():
                break

            score = self._detect(pcm)
            if score is None:
                continue

            logger.info("Wake word detected (score=%.2f).", score)
            return score

        return None

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
        self._microphone.close()
        sys.exit(0)
