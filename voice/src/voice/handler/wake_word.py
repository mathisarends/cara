import logging

from voice.events import (
    SessionEnded,
    SessionStarted,
    UserTurnStarted,
    WakeWordDetected,
)
from voice.events.bus import EventBus
from voice.events.models import VoiceTurnEnded, VoiceTurnRequested
from voice.wakeword import WakeWordListener

logger = logging.getLogger(__name__)


class WakeWordHandler:
    """Publishes wake words and starts a voice turn while the session is idle."""

    def __init__(self, *, event_bus: EventBus, source: WakeWordListener) -> None:
        self._event_bus = event_bus
        self._source = source
        self._session_active = False
        self._turn_active = False

        event_bus.on(SessionStarted, self._on_session_started)
        event_bus.on(SessionEnded, self._on_session_ended)
        event_bus.on(UserTurnStarted, self._on_user_turn_started)
        event_bus.on(VoiceTurnEnded, self._on_voice_turn_ended)

    async def run(self) -> None:
        async for detection in self._source.detections():
            logger.info(
                "Wake word %r detected (score=%.2f, sequence=%d)",
                detection.name,
                detection.score,
                detection.sequence,
            )
            if self._can_start_turn:
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
    def _can_start_turn(self) -> bool:
        return self._session_active and not self._turn_active

    async def _on_session_started(self, _: SessionStarted) -> None:
        self._session_active = True
        self._turn_active = False

    async def _on_session_ended(self, _: SessionEnded) -> None:
        self._session_active = False

    async def _on_user_turn_started(self, _: UserTurnStarted) -> None:
        self._turn_active = True

    async def _on_voice_turn_ended(self, _: VoiceTurnEnded) -> None:
        self._turn_active = False
