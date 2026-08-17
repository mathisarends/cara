from voice.events.bus import EventBus
from voice.events.models import VoiceResourcesClosing
from voice.stt import SpeechToText
from voice.tts import TextToSpeech


class SpeechResourceHandler:
    """Releases remote speech-provider resources at session shutdown."""

    def __init__(
        self,
        *,
        event_bus: EventBus,
        speech_to_text: SpeechToText,
        text_to_speech: TextToSpeech,
    ) -> None:
        self._speech_to_text = speech_to_text
        self._text_to_speech = text_to_speech

        # Separate subscriptions let the event bus close both providers concurrently.
        event_bus.on(VoiceResourcesClosing, self._close_speech_to_text)
        event_bus.on(VoiceResourcesClosing, self._close_text_to_speech)

    async def _close_speech_to_text(self, _: VoiceResourcesClosing) -> None:
        await self._speech_to_text.aclose()

    async def _close_text_to_speech(self, _: VoiceResourcesClosing) -> None:
        await self._text_to_speech.aclose()
