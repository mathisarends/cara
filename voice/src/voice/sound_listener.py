from transitbus import EventBus

from cara.events import AssistantInterrupted, SessionEnded
from voice.audio.earcons import Earcon, EarconPlayer


class SoundListener:
    """Plays earcons for assistant lifecycle events."""

    def __init__(self, event_bus: EventBus, earcons: EarconPlayer) -> None:
        self._earcons = earcons

        event_bus.on(AssistantInterrupted, self._on_assistant_interrupted)
        event_bus.on(SessionEnded, self._on_session_ended)

    async def _on_assistant_interrupted(self, event: AssistantInterrupted) -> None:
        await self._earcons.play(Earcon.INTERRUPT)

    async def _on_session_ended(self, event: SessionEnded) -> None:
        self._earcons.play_soon(Earcon.SLEEP)
