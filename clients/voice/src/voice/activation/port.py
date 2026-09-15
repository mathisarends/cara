from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass

from voice.activation_kind import ActivationKind


@dataclass(frozen=True, slots=True)
class ListenActivation:
    sequence: int | None = None
    speech_start_timeout: float | None = None
    kind: ActivationKind = ActivationKind.MANUAL


type Activation = ListenActivation


class ActivationSource(ABC):
    """Yields activations for as long as the source can produce them."""

    @abstractmethod
    def activations(self) -> AsyncIterator[Activation]: ...
