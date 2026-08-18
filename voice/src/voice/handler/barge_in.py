import logging

from voice.barge_in import BargeInSignal, BargeInStrategy
from voice.events import AssistantTurnStarted, SessionEnded
from voice.events.bus import EventBus
from voice.events.models import (
    VoiceTurnEnded,
    VoiceTurnInterrupted,
    VoiceTurnRequested,
)
from voice.handler.turn import TurnCoordinator

logger = logging.getLogger(__name__)


class BargeInHandler:
    """Hands the floor back to the user while the assistant is responding."""

    def __init__(
        self,
        *,
        event_bus: EventBus,
        strategy: BargeInStrategy,
        coordinator: TurnCoordinator,
    ) -> None:
        self._event_bus = event_bus
        self._strategy = strategy
        self._coordinator = coordinator
        self._armed = False

        event_bus.on(AssistantTurnStarted, self._on_assistant_turn_started)
        event_bus.on(VoiceTurnEnded, self._on_voice_turn_ended)
        event_bus.on(SessionEnded, self._on_session_ended)

    async def run(self) -> None:
        async for signal in self._strategy.signals():
            if not self._armed:
                continue
            await self._interrupt(signal)

    async def _interrupt(self, signal: BargeInSignal) -> None:
        self._armed = False
        turn_id = await self._coordinator.cancel_active_turn()
        if turn_id is None:
            return

        logger.info("Barge-in interrupted voice turn %d", turn_id)
        await self._event_bus.dispatch(VoiceTurnInterrupted(turn_id=turn_id))
        await self._event_bus.dispatch(VoiceTurnRequested(sequence=signal.sequence))

    async def _on_assistant_turn_started(self, _: AssistantTurnStarted) -> None:
        self._armed = True

    async def _on_voice_turn_ended(self, _: VoiceTurnEnded) -> None:
        self._armed = False

    async def _on_session_ended(self, _: SessionEnded) -> None:
        self._armed = False
