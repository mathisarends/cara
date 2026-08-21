from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ListenActivation:
    sequence: int | None = None
    speech_start_timeout: float | None = None


@dataclass(frozen=True, slots=True)
class PromptActivation:
    prompt: str


type Activation = ListenActivation | PromptActivation


class ActivationSource(ABC):
    """Yields activations for as long as the source can produce them."""

    @abstractmethod
    def activations(self) -> AsyncIterator[Activation]: ...
