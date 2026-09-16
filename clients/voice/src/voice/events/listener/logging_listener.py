import logging

from voice.events import (
    SessionStarted,
    VoiceConversationEnded,
    VoiceConversationInactivityCountdown,
)
from voice.events.bus import EventBus

logger = logging.getLogger(__name__)


class LoggingListener:
    """Logs user-facing voice-session status changes."""

    def __init__(self, event_bus: EventBus, *, wake_word_phrase: str) -> None:
        self._wake_word_phrase = wake_word_phrase.title()
        event_bus.on(SessionStarted, self._on_session_started)
        event_bus.on(
            VoiceConversationInactivityCountdown,
            self._on_conversation_inactivity_countdown,
        )
        event_bus.on(VoiceConversationEnded, self._on_conversation_ended)

    async def _on_session_started(self, _: SessionStarted) -> None:
        self._log_listening()

    async def _on_conversation_inactivity_countdown(
        self,
        event: VoiceConversationInactivityCountdown,
    ) -> None:
        logger.info("Voice conversation timeout in %d", event.remaining_seconds)

    async def _on_conversation_ended(self, _: VoiceConversationEnded) -> None:
        self._log_listening()

    def _log_listening(self) -> None:
        logger.info('Listening for "%s". Press Ctrl+C to quit.', self._wake_word_phrase)
