from agent.events import AssistantInterrupted
from voice.audio import PlaybackCoordinator
from voice.events.bus import EventBus
from voice.events.models import VoiceInterruptionRequested
from voice.pipeline import TurnController


class InterruptionHandler:
    """Interrupts an active turn when another wake word is detected."""

    def __init__(
        self,
        *,
        event_bus: EventBus,
        turns: TurnController,
        playback: PlaybackCoordinator,
    ) -> None:
        self._event_bus = event_bus
        self._turns = turns
        self._playback = playback

        event_bus.on(VoiceInterruptionRequested, self._on_interruption_requested)

    async def _on_interruption_requested(self, _: VoiceInterruptionRequested) -> None:
        if not self._turns.has_active_turn:
            return

        await self._playback.interrupt()
        await self._turns.interrupt()
        await self._event_bus.dispatch(AssistantInterrupted())
