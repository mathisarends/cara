from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class BargeInSignal:
    """Marks the captured audio position at which the user took the floor."""

    sequence: int


class BargeInStrategy(ABC):
    """Detects that the user interrupts while the assistant holds the floor."""

    @abstractmethod
    def signals(self) -> AsyncIterator[BargeInSignal]:
        """Yield one signal per interruption for as long as the session runs."""
