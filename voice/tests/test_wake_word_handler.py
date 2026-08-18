import asyncio
from collections.abc import AsyncIterator

from voice.events import SessionStarted, UserTurnStarted, WakeWordDetected
from voice.events.bus import EventBus
from voice.events.models import VoiceTurnRequested
from voice.handler import WakeWordHandler
from voice.wakeword import WakeWordDetection


class _WakeWords:
    async def detections(self) -> AsyncIterator[WakeWordDetection]:
        yield WakeWordDetection(sequence=1, score=0.9, name="hey_mycroft")
        yield WakeWordDetection(sequence=2, score=0.9, name="hey_mycroft")


def test_ignores_wake_words_during_an_active_turn() -> None:
    async def run() -> list[WakeWordDetected]:
        event_bus = EventBus()
        detections: list[WakeWordDetected] = []

        async def start_turn(_: VoiceTurnRequested) -> None:
            await event_bus.dispatch(UserTurnStarted())

        async def record_detection(event: WakeWordDetected) -> None:
            detections.append(event)

        event_bus.on(VoiceTurnRequested, start_turn)
        event_bus.on(WakeWordDetected, record_detection)
        handler = WakeWordHandler(event_bus=event_bus, source=_WakeWords())

        await event_bus.dispatch(SessionStarted())
        await handler.run()
        return detections

    detections = asyncio.run(run())

    assert [event.sequence for event in detections] == [1]
