import asyncio
from abc import ABC, abstractmethod


class WakeWordDetectionSource(ABC):
    @abstractmethod
    async def detect_once(self, *, cancel: asyncio.Event | None = None) -> float | None:
        """Listen until the wake word is detected or cancellation is requested."""
