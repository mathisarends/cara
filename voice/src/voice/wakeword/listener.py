from collections.abc import AsyncIterator

from wakewordkit import AudioFormat as DetectorAudioFormat
from wakewordkit import WakeWord, WakeWordDetector

from voice.audio.hub import AudioHub, AudioOverrunError
from voice.wakeword.models import WakeWordDetection, WakeWordSettings

_WAKE_WORD_PHRASES = {
    WakeWord.ALEXA: "alexa",
    WakeWord.HEY_JARVIS: "hey jarvis",
    WakeWord.HEY_MYCROFT: "hey mycroft",
    WakeWord.HEY_MARVIN: "hey marvin",
}


class WakeWordListener:
    """Runs wake-word inference from an AudioHub cursor without owning a device."""

    def __init__(
        self,
        hub: AudioHub,
        *,
        settings: WakeWordSettings,
    ) -> None:
        self._hub = hub
        self._phrase = _WAKE_WORD_PHRASES[settings.wake_word]
        self._detector = WakeWordDetector(
            settings.wake_word,
            threshold=settings.sensitivity,
            cooldown=settings.cooldown,
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
