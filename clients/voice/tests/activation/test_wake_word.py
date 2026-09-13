import asyncio
from collections.abc import AsyncIterator
from typing import cast

from voice.activation import WakeWordActivationSource
from voice.events import WakeWordDetected
from voice.events.bus import EventBus
from voice.wakeword import WakeWordDetection, WakeWordListener


class _WakeWords:
    async def detections(self) -> AsyncIterator[WakeWordDetection]:
        yield WakeWordDetection(sequence=1, score=0.9, name="hey_mycroft")
        yield WakeWordDetection(sequence=2, score=0.8, name="hey_mycroft")


def test_publishes_every_detection_after_its_activation() -> None:
    async def run() -> list[str]:
        event_bus = EventBus()
        observed: list[str] = []

        async def record_detection(event: WakeWordDetected) -> None:
            observed.append(f"detected:{event.sequence}")

        event_bus.on(WakeWordDetected, record_detection)
        source = WakeWordActivationSource(
            event_bus=event_bus,
            listener=cast(WakeWordListener, _WakeWords()),
        )

        async for activation in source.activations():
            observed.append(f"activated:{activation.sequence}")
        return observed

    assert asyncio.run(run()) == [
        "activated:1",
        "detected:1",
        "activated:2",
        "detected:2",
    ]
