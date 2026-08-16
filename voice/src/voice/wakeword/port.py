from abc import ABC, abstractmethod
from collections.abc import AsyncIterator

from voice.wakeword.models import WakeWordDetection


class WakeWordSource(ABC):
    @property
    @abstractmethod
    def phrase(self) -> str:
        """Return the exact phrase expected at the start of a transcript."""

    @abstractmethod
    def detections(self) -> AsyncIterator[WakeWordDetection]:
        """Yield detections while the shared audio capture is running."""
