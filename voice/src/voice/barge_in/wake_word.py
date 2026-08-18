import asyncio
import contextlib
from collections.abc import AsyncIterator

from voice.barge_in.port import BargeInSignal, BargeInStrategy
from voice.events import WakeWordDetected
from voice.events.bus import EventBus


class WakeWordBargeIn(BargeInStrategy):
    """Treats the wake word as an interruption while the assistant responds."""

    def __init__(self, *, event_bus: EventBus) -> None:
        self._signals: asyncio.Queue[BargeInSignal] = asyncio.Queue(maxsize=1)
        event_bus.on(WakeWordDetected, self._on_wake_word_detected)

    async def signals(self) -> AsyncIterator[BargeInSignal]:
        while True:
            yield await self._signals.get()

    async def _on_wake_word_detected(self, event: WakeWordDetected) -> None:
        # A queued signal already interrupts the same turn, so drop repeats.
        with contextlib.suppress(asyncio.QueueFull):
            self._signals.put_nowait(BargeInSignal(sequence=event.sequence))
