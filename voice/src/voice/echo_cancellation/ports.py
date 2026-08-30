from abc import ABC, abstractmethod
from collections.abc import Callable

type Clock = Callable[[], float]


class EchoCanceller(ABC):
    @abstractmethod
    def process(self, near_end: bytes, far_end: bytes) -> bytes: ...

    def reset(self) -> None:  # noqa: B027 - stateless filters need no reset
        pass


class EchoPresence(ABC):
    """Reports how much of the captured audio is the assistant's own playback."""

    @property
    @abstractmethod
    def echo_confidence(self) -> float:
        """The playback's share of the recent microphone audio, in 0..1.

        Answers whether our own sound is in the room right now, which is a
        separate question from whether cancelling it succeeded.
        """
