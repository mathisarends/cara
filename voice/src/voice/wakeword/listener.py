from collections.abc import AsyncIterator

from wakewordkit import AudioFormat as DetectorAudioFormat
from wakewordkit import WakeWord, WakeWordDetector

from voice.audio.buffered_input import AudioOverrunError, BufferedAudioInput
from voice.wakeword.models import WakeWordDetection, WakeWordSettings

_WAKE_WORD_PHRASES = {
    WakeWord.ALEXA: "alexa",
    WakeWord.HEY_JARVIS: "hey jarvis",
    WakeWord.HEY_MYCROFT: "hey mycroft",
    WakeWord.HEY_MARVIN: "hey marvin",
}


class WakeWordListener:
    """Runs wake-word inference from buffered input without owning a device."""

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

    @property
    def phrase(self) -> str:
        return self._phrase

    async def detections(self) -> AsyncIterator[WakeWordDetection]:
        while self._buffered_audio_input.is_running:
            cursor = await self._buffered_audio_input.cursor()
            try:
                async for frame in cursor:
                    detection = await self._detector.process(
                        frame.pcm,
                        format=DetectorAudioFormat(
                            sample_rate=self._buffered_audio_input.sample_rate,
                            channels=self._buffered_audio_input.channels,
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
