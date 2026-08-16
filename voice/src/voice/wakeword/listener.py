from collections.abc import AsyncIterator

from wakewordkit import AudioFormat as DetectorAudioFormat
from wakewordkit import WakeWord, WakeWordDetector

from voice.audio.hub import AudioHub, AudioOverrunError
from voice.pipeline.models import WakeWordDetection


class WakeWordListener:
    """Runs wake-word inference from an AudioHub cursor without owning a device."""

    def __init__(
        self,
        hub: AudioHub,
        *,
        wake_word: WakeWord = WakeWord.HEY_MYCROFT,
        sensitivity: float = 0.5,
        cooldown: float = 1.5,
    ) -> None:
        self._hub = hub
        self._phrase = wake_word.label.replace("_", " ")
        self._detector = WakeWordDetector(
            wake_word, threshold=sensitivity, cooldown=cooldown
        )

    @property
    def phrase(self) -> str:
        return self._phrase

    async def detections(self) -> AsyncIterator[WakeWordDetection]:
        while self._hub.is_running:
            cursor = await self._hub.cursor()
            try:
                async for frame in cursor:
                    detection = await self._detector.process(
                        frame.pcm,
                        format=DetectorAudioFormat(
                            sample_rate=self._hub.format.sample_rate,
                            channels=self._hub.format.channels,
                            sample_format="pcm_s16le",
                        ),
                    )
                    if detection is not None:
                        yield WakeWordDetection(
                            sequence=frame.sequence,
                            score=detection.score,
                            name=detection.name,
                        )
            except AudioOverrunError:
                self._detector.reset()
            finally:
                await cursor.aclose()
