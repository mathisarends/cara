import asyncio
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator


class WakeWordDetectionSource(ABC):
    @abstractmethod
    async def detect_once(self, *, cancel: asyncio.Event | None = None) -> float | None:
        """Listen until the wake word is detected or cancellation is requested."""


class WakeWordSessionSource(ABC):
    @abstractmethod
    def detections(self) -> AsyncIterator[float]:
        """Yield every wake-word detection used to start a voice session."""
