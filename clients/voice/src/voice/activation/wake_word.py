import logging
from collections.abc import AsyncIterator

from voice.activation.port import Activation, ActivationSource, ListenActivation
from voice.events import WakeWordDetected
from voice.events.bus import EventBus
from voice.wakeword import WakeWordListener

logger = logging.getLogger(__name__)


class WakeWordActivationSource(ActivationSource):
    """Activates on the wake word and publishes every detection for barge-in."""

    def __init__(self, *, event_bus: EventBus, listener: WakeWordListener) -> None:
        self._event_bus = event_bus
        self._listener = listener

    async def activations(self) -> AsyncIterator[Activation]:
        async for detection in self._listener.detections():
            logger.info(
                "Wake word %r detected (score=%.2f, sequence=%d)",
                detection.name,
                detection.score,
                detection.sequence,
            )
            # Detections are published after the activation so that a wake word
            # arriving mid-turn reaches barge-in as an interruption rather than
            # racing the turn it would otherwise have started.
            yield ListenActivation(sequence=detection.sequence)
            await self._event_bus.dispatch(
                WakeWordDetected(
                    score=detection.score,
                    sequence=detection.sequence,
                    name=detection.name,
                )
            )
