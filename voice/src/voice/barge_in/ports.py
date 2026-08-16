import asyncio
from typing import Protocol


class BargeIn(Protocol):
    """Detects when the user wants to interrupt the active response."""

    async def wait(self, *, cancel: asyncio.Event) -> None:
        """Return after an interruption is detected or cancellation is requested."""
        ...
