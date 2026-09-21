import logging
import math
import time
from collections.abc import AsyncIterator

from wakewordkit import AudioFormat as DetectorAudioFormat
from wakewordkit import WakeWord, WakeWordDetector

from voice.audio.buffered_input import AudioOverrunError, BufferedAudioInput
from voice.wakeword.models import WakeWordDetection, WakeWordSettings

logger = logging.getLogger(__name__)

_WAKE_WORD_PHRASES = {
    WakeWord.ALEXA: "alexa",
    WakeWord.HEY_JARVIS: "hey jarvis",
    WakeWord.HEY_MYCROFT: "hey mycroft",
    WakeWord.HEY_MARVIN: "hey marvin",
}


class WakeWordListener:
    def __init__(
        self,
        buffered_audio_input: BufferedAudioInput,
        *,
        settings: WakeWordSettings,
    ) -> None:
        self._buffered_audio_input = buffered_audio_input
        self._phrase = _WAKE_WORD_PHRASES[settings.wake_word]
        self._detector = WakeWordDetector(
            settings.wake_word,
            threshold=settings.sensitivity,
            cooldown=settings.cooldown,
        )
        # Chunks, not seconds: wall-clock time can balloon relative to audio
        # content when something else stalls the event loop (e.g. a blocking
        # HTTP call), which would let a cooldown measured in wall-clock time
        # expire early and let the same utterance's tail re-trigger.
        self._cooldown_chunks = max(
            1, math.ceil(settings.cooldown / buffered_audio_input.chunk_seconds)
        )
        self._last_detection_sequence: int | None = None
        self._last_yield_at: float | None = None

    @property
    def phrase(self) -> str:
        return self._phrase

    async def detections(self) -> AsyncIterator[WakeWordDetection]:
        while self._buffered_audio_input.is_running:
            reader = await self._buffered_audio_input.open_reader()
            try:
                async for frame in reader:
                    before = time.monotonic()
                    detection = await self._detector.process(
                        frame.pcm,
                        format=DetectorAudioFormat(
                            sample_rate=self._buffered_audio_input.sample_rate,
                            channels=self._buffered_audio_input.channels,
                            sample_format="pcm_s16le",
                        ),
                    )
                    after = time.monotonic()
                    if detection is not None and self._is_past_cooldown(frame.sequence):
                        now = time.monotonic()
                        gap = (
                            None
                            if self._last_yield_at is None
                            else now - self._last_yield_at
                        )
                        logger.debug(
                            "Wake-word candidate sequence=%d score=%.2f "
                            "gap_since_last=%s process_latency=%.3fs",
                            frame.sequence,
                            detection.score,
                            f"{gap:.3f}s" if gap is not None else "n/a",
                            after - before,
                        )
                        self._last_yield_at = now
                        yield WakeWordDetection(
                            sequence=frame.sequence,
                            score=detection.score,
                            name=detection.name,
                        )
            except AudioOverrunError:
                logger.warning(
                    "Wake-word reader overran the audio buffer; resetting detector"
                )
                self._detector.reset()
            finally:
                await reader.aclose()

    def _is_past_cooldown(self, sequence: int) -> bool:
        if (
            self._last_detection_sequence is not None
            and sequence - self._last_detection_sequence < self._cooldown_chunks
        ):
            return False
        self._last_detection_sequence = sequence
        return True
