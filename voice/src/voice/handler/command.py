import logging
import re

from voice.events import (
    AssistantResponseRequested,
    AssistantTurnStarted,
    UserTranscriptionCompleted,
)
from voice.events.bus import EventBus

logger = logging.getLogger(__name__)


class CommandBridge:
    """Turns final user transcriptions into assistant response requests."""

    def __init__(
        self,
        *,
        event_bus: EventBus,
        wake_word_phrase: str,
        strip_wake_word: bool = True,
    ) -> None:
        self._event_bus = event_bus
        self._wake_word_phrase = wake_word_phrase
        self._strip_wake_word = strip_wake_word

        event_bus.on(UserTranscriptionCompleted, self._on_transcription_completed)

    async def _on_transcription_completed(
        self, event: UserTranscriptionCompleted
    ) -> None:
        text = _prepare_command(
            event.text,
            self._wake_word_phrase,
            strip_wake_word=self._strip_wake_word,
        )
        logger.debug("Turn %d: user said %r", event.turn_id, text)
        await self._event_bus.dispatch(AssistantTurnStarted())
        await self._event_bus.dispatch(
            AssistantResponseRequested(turn_id=event.turn_id, text=text)
        )


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
