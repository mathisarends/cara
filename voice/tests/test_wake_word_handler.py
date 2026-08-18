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


def test_starts_no_second_turn_while_one_is_active() -> None:
    async def run() -> tuple[list[VoiceTurnRequested], list[WakeWordDetected]]:
        event_bus = EventBus()
        requests: list[VoiceTurnRequested] = []
        detections: list[WakeWordDetected] = []

        async def start_turn(event: VoiceTurnRequested) -> None:
            requests.append(event)
            await event_bus.dispatch(UserTurnStarted())

        async def record_detection(event: WakeWordDetected) -> None:
            detections.append(event)

        event_bus.on(VoiceTurnRequested, start_turn)
        event_bus.on(WakeWordDetected, record_detection)
        handler = WakeWordHandler(event_bus=event_bus, source=_WakeWords())

        await event_bus.dispatch(SessionStarted())
        await handler.run()
        return requests, detections

    requests, detections = asyncio.run(run())

    assert [event.sequence for event in requests] == [1]
    assert [event.sequence for event in detections] == [1, 2]
