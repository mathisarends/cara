import asyncio
from collections.abc import AsyncIterator

from voice.activation.port import (
    Activation,
    ActivationSource,
    ListenActivation,
)


class ExternalActivationSource(ActivationSource):
    """Activates on demand, for buttons, hotkeys and other out-of-band triggers."""

    def __init__(self) -> None:
        self._activations: asyncio.Queue[Activation] = asyncio.Queue()

    async def activate(self, *, speech_start_timeout: float | None = None) -> None:
        """Listen to the user, starting at live audio rather than at past history."""
        await self._activations.put(
            ListenActivation(speech_start_timeout=speech_start_timeout)
        )

    async def activations(self) -> AsyncIterator[Activation]:
        while True:
            yield await self._activations.get()
