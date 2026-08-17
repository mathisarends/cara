import logging

from agent.events import SessionEnded, SessionStarted, UserSpeechEnded, UserTurnStarted
from voice.events import WakeWordDetected
from voice.events.bus import EventBus
from voice.events.models import (
    VoiceInterruptionRequested,
    VoiceTurnEnded,
    VoiceTurnRequested,
)
from voice.wakeword import WakeWordListener

logger = logging.getLogger(__name__)


class WakeWordHandler:
    """Publishes wake words while the session is not listening to a user turn."""

    def __init__(self, *, event_bus: EventBus, source: WakeWordListener) -> None:
        self._event_bus = event_bus
        self._source = source
        self._session_active = False
        self._listening = False

        event_bus.on(SessionStarted, self._on_session_started)
        event_bus.on(SessionEnded, self._on_session_ended)
        event_bus.on(UserTurnStarted, self._on_user_turn_started)
        event_bus.on(UserSpeechEnded, self._on_user_speech_ended)
        event_bus.on(VoiceTurnEnded, self._on_voice_turn_ended)

    async def run(self) -> None:
        async for detection in self._source.detections():
            if not self._is_enabled:
                continue

            logger.info(
                "Wake word %r detected (score=%.2f, sequence=%d)",
                detection.name,
                detection.score,
                detection.sequence,
            )
            await self._event_bus.dispatch(VoiceInterruptionRequested())
            if self._session_active:
                await self._event_bus.dispatch(
                    VoiceTurnRequested(sequence=detection.sequence)
                )
                await self._event_bus.dispatch(
                    WakeWordDetected(
                        score=detection.score,
                        sequence=detection.sequence,
                        name=detection.name,
                    )
                )

    def close(self) -> None:
        self._session_active = False

    @property
    def _is_enabled(self) -> bool:
        return self._session_active and not self._listening

    async def _on_session_started(self, _: SessionStarted) -> None:
        self._session_active = True
        self._listening = False

    async def _on_session_ended(self, _: SessionEnded) -> None:
        self._session_active = False

    async def _on_user_turn_started(self, _: UserTurnStarted) -> None:
        self._listening = True

    async def _on_user_speech_ended(self, _: UserSpeechEnded) -> None:
        self._listening = False

    async def _on_voice_turn_ended(self, _: VoiceTurnEnded) -> None:
        self._listening = False
