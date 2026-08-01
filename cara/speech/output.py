import asyncio
import logging

from transitbus import EventBus
from vocalbin import TextToSpeech, TextToSpeechFormat, TextToSpeechRequest

from cara.audio import AudioPlayback
from cara.events import AssistantSpeechStarted
from cara.speech.settings import SpeechSettings

logger = logging.getLogger(__name__)


class SpeechOutput:
    """Synthesizes text and plays it through an audio destination."""

    def __init__(
        self,
        tts: TextToSpeech,
        player: AudioPlayback,
        settings: SpeechSettings,
        event_bus: EventBus,
    ) -> None:
        self._tts = tts
        self._player = player
        self._settings = settings
        self._event_bus = event_bus

    async def send(self, text: str, *, cancel: asyncio.Event | None = None) -> None:
        logger.info("[says] %s", text)
        response = await self._tts.synthesize(
            TextToSpeechRequest(
                text=text,
                voice=self._settings.tts_voice,
                response_format=TextToSpeechFormat.WAV,
                instructions=self._settings.tts_voice_instructions,
            )
        )
        await self._event_bus.dispatch(AssistantSpeechStarted())
        await self._player.play(response.audio, cancel=cancel)
