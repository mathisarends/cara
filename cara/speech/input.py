import logging
import threading

from transitbus import EventBus
from vocalbin import SpeechToText, SpeechToTextRequest

from cara.audio import SpeechRecorder
from cara.events import UserSpeechEnded, UserSpeechStarted
from cara.speech.settings import SpeechSettings

logger = logging.getLogger(__name__)


class SpeechInput:
    """Turns one recorded user utterance into text."""

    def __init__(
        self,
        recorder: SpeechRecorder,
        stt: SpeechToText,
        settings: SpeechSettings,
        event_bus: EventBus,
    ) -> None:
        self._recorder = recorder
        self._stt = stt
        self._settings = settings
        self._event_bus = event_bus

    async def receive(
        self,
        *,
        initial_silence_timeout: float | None = None,
        ready: threading.Event | None = None,
    ) -> str | None:
        audio = await self._recorder.record_until_silence(
            initial_silence_timeout=initial_silence_timeout,
            ready=ready,
            on_speech_started=self._on_speech_started,
        )
        if audio is None:
            return None

        await self._event_bus.dispatch(UserSpeechEnded())
        response = await self._stt.transcribe(
            SpeechToTextRequest(audio=audio, language=self._settings.language),
        )
        transcript = response.text.strip()
        if transcript:
            logger.info("[heard] %s", transcript)
        return transcript

    async def _on_speech_started(self) -> None:
        await self._event_bus.dispatch(UserSpeechStarted())
