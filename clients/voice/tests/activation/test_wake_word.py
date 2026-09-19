import asyncio
from collections.abc import AsyncIterator
from typing import cast

from voice.activation import (
    ActivationKind,
    ListenActivation,
    WakeWordActivationSource,
)
from voice.wakeword import WakeWordDetection, WakeWordListener

_DETECTIONS = (
    WakeWordDetection(sequence=1, score=0.9, name="hey_mycroft"),
    WakeWordDetection(sequence=2, score=0.8, name="hey_mycroft"),
)


class _WakeWords:
    async def detections(self) -> AsyncIterator[WakeWordDetection]:
        for detection in _DETECTIONS:
            yield detection


def test_activates_on_every_detection() -> None:
    async def run() -> list[ListenActivation]:
        source = WakeWordActivationSource(cast(WakeWordListener, _WakeWords()))
        return [activation async for activation in source.activations()]

    assert asyncio.run(run()) == [
        ListenActivation(
            sequence=detection.sequence,
            kind=ActivationKind.WAKE_WORD,
            detection=detection,
        )
        for detection in _DETECTIONS
    ]
