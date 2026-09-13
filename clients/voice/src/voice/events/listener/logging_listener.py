import logging

from voice.events import (
    FollowUpCountdown,
    FollowUpTimedOut,
    SessionStarted,
)
from voice.events.bus import EventBus
from voice.events.models import VoiceTurnEnded

logger = logging.getLogger(__name__)


class LoggingListener:
    """Logs user-facing voice-session status changes."""

    def __init__(self, event_bus: EventBus, *, wake_word_phrase: str) -> None:
        self._wake_word_phrase = wake_word_phrase.title()
        self._follow_up_timed_out = False

        event_bus.on(SessionStarted, self._on_session_started)
        event_bus.on(FollowUpCountdown, self._on_follow_up_countdown)
        event_bus.on(FollowUpTimedOut, self._on_follow_up_timed_out)
        event_bus.on(VoiceTurnEnded, self._on_voice_turn_ended)

    async def _on_session_started(self, _: SessionStarted) -> None:
        self._log_listening()

    async def _on_follow_up_countdown(self, event: FollowUpCountdown) -> None:
        logger.info("Follow-up timeout in %d", event.remaining_seconds)

    async def _on_follow_up_timed_out(self, _: FollowUpTimedOut) -> None:
        self._follow_up_timed_out = True

    async def _on_voice_turn_ended(self, _: VoiceTurnEnded) -> None:
        if not self._follow_up_timed_out:
            return
        self._follow_up_timed_out = False
        self._log_listening()

    def _log_listening(self) -> None:
        logger.info('Listening for "%s". Press Ctrl+C to quit.', self._wake_word_phrase)
