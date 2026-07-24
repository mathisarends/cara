import asyncio
import logging
import signal
import sys
from collections.abc import AsyncIterator

from wakewordkit import WakeWord, WakeWordDetector

from cara.audio import MicrophoneStream
from cara.wakeword.ports import WakeWordDetectionSource

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
        self._microphone = microphone
        self._wake_word = wake_word
        self._detector = WakeWordDetector(wake_word, threshold=sensitivity)

    async def detections(self) -> AsyncIterator[float]:
        """Yield the detection score once per wake-word detection.

        The microphone stream is shared with the recorder, so detection simply
        stops reading while a detection is handled and resumes afterwards; the
        capture itself never pauses.
        """
        logger.info('Listening for "%s"...', self._wake_word.label)

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
            logger.info('Listening for "%s"...', self._wake_word.label)

    async def detect_once(self, *, cancel: asyncio.Event | None = None) -> float | None:
        """Listen until the wake word is detected or cancellation is requested."""
        self._detector.reset()
        loop = asyncio.get_running_loop()
        while cancel is None or not cancel.is_set():
            pcm = await loop.run_in_executor(None, self._microphone.read, _PREDICTION_CHUNK)

            if cancel is not None and cancel.is_set():
                break

            detection = self._detector.process(pcm)
            if detection is None:
                continue

            logger.info("Wake word detected (score=%.2f).", detection.score)
            return detection.score

        return None

    def _shutdown(self) -> None:
        logger.info("Shutting down...")
        self._microphone.close()
        sys.exit(0)
