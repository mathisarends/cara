from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass

from voice.activation import Activation


@dataclass(frozen=True, slots=True)
class BargeInSignal:
    """Marks the captured audio position at which the user took the floor."""

    sequence: int


class BargeInStrategy(ABC):
    """Detects that the user takes the floor while the assistant holds it.

    A strategy only reports candidates; the runtime decides whether the
    assistant is responding and the interruption therefore applies.
    """

    @abstractmethod
    def signals(self) -> AsyncIterator[BargeInSignal]:
        """Yield one signal per detected interruption."""

    def interruption_for(self, activation: Activation) -> BargeInSignal | None:
        """Return the interruption an activation stands for, if any.

        Activations are otherwise rejected while a turn is active; a strategy
        that reuses an activation source overrides this.
        """
        return None
