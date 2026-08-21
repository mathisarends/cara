from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Activation:
    """A request to take the floor, independent of what triggered it."""

    sequence: int | None = None
    speech_start_timeout: float | None = None


class ActivationSource(ABC):
    """Yields activations for as long as the source can produce them."""

    @abstractmethod
    def activations(self) -> AsyncIterator[Activation]: ...
