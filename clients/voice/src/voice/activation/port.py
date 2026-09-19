from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass
from enum import StrEnum

from voice.wakeword.models import WakeWordDetection


class ActivationKind(StrEnum):
    WAKE_WORD = "wake_word"
    MANUAL = "manual"
    FOLLOW_UP = "follow_up"
    BARGE_IN = "barge_in"


@dataclass(frozen=True, slots=True)
class ListenActivation:
    sequence: int | None = None
    speech_start_timeout: float | None = None
    kind: ActivationKind = ActivationKind.MANUAL
    # Observers learn about the detection even when the runtime rejects the
    # activation, for example while a turn is already active.
    detection: WakeWordDetection | None = None


type Activation = ListenActivation


class ActivationSource(ABC):
    """Yields activations for as long as the source can produce them."""

    @abstractmethod
    def activations(self) -> AsyncIterator[Activation]: ...
