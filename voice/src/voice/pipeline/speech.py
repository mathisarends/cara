import asyncio
import logging
import re
from collections.abc import AsyncIterator

from voice.audio.hub import AudioCursor
from voice.events import (
    AssistantResponseRequested,
    AssistantTurnStarted,
    UserAudioChunk,
    UserSpeechEnded,
    UserSpeechStarted,
    UserTranscriptionUpdated,
    VoiceTurnTimedOut,
)
from voice.events.bus import EventBus
from voice.stt import SpeechToText, Transcription

logger = logging.getLogger(__name__)


class SpeechPipeline:
    """Transforms captured audio into realtime transcription events."""

    def __init__(
        self,
        *,
        wake_word_phrase: str,
        strip_wake_word: bool = True,
        speech_to_text: SpeechToText,
        event_bus: EventBus,
    ) -> None:
        self._wake_word_phrase = wake_word_phrase
        self._strip_wake_word = strip_wake_word
        self._stt = speech_to_text
        self._event_bus = event_bus

    async def run(
        self,
        *,
        turn_id: int,
        audio: AudioCursor,
        speech_start_timeout: float,
    ) -> None:
        transcriptions = self._stt.transcribe(
            _publish_user_audio(audio, self._event_bus, turn_id)
        )
        try:
            try:
                first = await asyncio.wait_for(
                    anext(transcriptions), timeout=speech_start_timeout
                )
            except TimeoutError:
                logger.debug(
                    "Turn %d: no speech within %.1fs, timing out",
                    turn_id,
                    speech_start_timeout,
                )
                await self._event_bus.dispatch(VoiceTurnTimedOut(turn_id=turn_id))
                return
            except StopAsyncIteration:
                return

            await self._publish_transcription(turn_id, first)
            await self._event_bus.dispatch(UserSpeechStarted())
            final_text = first.text if first.is_final else None
            while final_text is None:
                update = await anext(transcriptions)
                await self._publish_transcription(turn_id, update)
                if update.is_final:
                    final_text = update.text

            await self._event_bus.dispatch(UserSpeechEnded())
            text = _prepare_command(
                final_text,
                self._wake_word_phrase,
                strip_wake_word=self._strip_wake_word,
            )
            logger.debug("Turn %d: user said %r", turn_id, text)
            await self._event_bus.dispatch(AssistantTurnStarted())
            await self._event_bus.dispatch(
                AssistantResponseRequested(turn_id=turn_id, text=text)
            )
        finally:
            await transcriptions.aclose()

    async def _publish_transcription(self, turn_id: int, update: Transcription) -> None:
        await self._event_bus.dispatch(
            UserTranscriptionUpdated(
                turn_id=turn_id,
                text=update.text,
                is_final=update.is_final,
                kind=update.kind,
            )
        )


async def _publish_user_audio(
    cursor: AudioCursor, event_bus: EventBus, turn_id: int
) -> AsyncIterator[bytes]:
    async for frame in cursor:
        await event_bus.dispatch(UserAudioChunk(turn_id=turn_id, chunk=frame.pcm))
        yield frame.pcm


def _strip_known_wake_word(text: str, phrase: str) -> str:
    if not phrase:
        return text.strip()
    pattern = rf"^\s*{re.escape(phrase)}(?=\s|[,.:;!?-]|$)[\s,.:;!?-]*"
    return re.sub(pattern, "", text, count=1, flags=re.IGNORECASE).strip()


def _prepare_command(text: str, wake_word_phrase: str, *, strip_wake_word: bool) -> str:
    text = text.strip()
    if not strip_wake_word:
        return text
    return _strip_known_wake_word(text, wake_word_phrase)
