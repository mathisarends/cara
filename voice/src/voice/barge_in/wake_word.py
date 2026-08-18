from collections.abc import AsyncIterator

from voice.barge_in.port import (
    BargeInContext,
    BargeInSignal,
    BargeInStrategy,
    PendingSignal,
)
from voice.events import WakeWordDetected


class WakeWordBargeIn(BargeInStrategy):
    """Treats the wake word as an interruption while the assistant responds."""

    def __init__(self) -> None:
        self._pending = PendingSignal()

    def set_context(self, context: BargeInContext) -> None:
        context.event_bus.on(WakeWordDetected, self._on_wake_word_detected)

    def signals(self) -> AsyncIterator[BargeInSignal]:
        return self._pending.stream()

    async def _on_wake_word_detected(self, event: WakeWordDetected) -> None:
        self._pending.put(event.sequence)
