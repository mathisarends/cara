from collections.abc import AsyncIterator

from voice.activation import Activation, ActivationKind
from voice.barge_in.port import BargeInSignal, BargeInStrategy


class WakeWordBargeIn(BargeInStrategy):
    """Treats the wake word as an interruption while the assistant responds."""

    async def signals(self) -> AsyncIterator[BargeInSignal]:
        # Wake words already arrive as activations, so a second detector
        # listening for them would only duplicate the work.
        return
        yield  # Unreachable, but makes this an empty async generator.

    def interruption_for(self, activation: Activation) -> BargeInSignal | None:
        if activation.kind is not ActivationKind.WAKE_WORD:
            return None
        if activation.sequence is None:
            return None
        return BargeInSignal(sequence=activation.sequence)
