import logging
from collections.abc import AsyncIterator

from voice.activation.port import (
    Activation,
    ActivationKind,
    ActivationSource,
    ListenActivation,
)
from voice.wakeword import WakeWordListener

logger = logging.getLogger(__name__)


class WakeWordActivationSource(ActivationSource):
    """Activates on every wake word detection."""

    def __init__(self, listener: WakeWordListener) -> None:
        self._listener = listener

    async def activations(self) -> AsyncIterator[Activation]:
        async for detection in self._listener.detections():
            logger.info(
                "Wake word %r detected (score=%.2f, sequence=%d)",
                detection.name,
                detection.score,
                detection.sequence,
            )
            yield ListenActivation(
                sequence=detection.sequence,
                kind=ActivationKind.WAKE_WORD,
                detection=detection,
            )
