import logging

from voice.lifecycle.events import (
    SessionStarted,
    VoiceConversationEnded,
    VoiceConversationInactivityCountdown,
    VoiceLifecycleEvent,
)
from voice.lifecycle.observer import VoiceLifecycleObserver

logger = logging.getLogger(__name__)


class LoggingObserver(VoiceLifecycleObserver):
    """Logs user-facing voice-session status changes."""

    def __init__(self, *, wake_word_phrase: str) -> None:
        self._wake_word_phrase = wake_word_phrase.title()

    async def on_lifecycle_event(self, event: VoiceLifecycleEvent) -> None:
        match event:
            case SessionStarted() | VoiceConversationEnded():
                logger.info(
                    'Listening for "%s". Press Ctrl+C to quit.',
                    self._wake_word_phrase,
                )
            case VoiceConversationInactivityCountdown(remaining_seconds=remaining):
                logger.info("Voice conversation timeout in %d", remaining)
