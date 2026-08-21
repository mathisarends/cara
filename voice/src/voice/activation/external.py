import asyncio
from collections.abc import AsyncIterator

from voice.activation.port import Activation, ActivationSource


class ExternalActivationSource(ActivationSource):
    """Activates on demand, for buttons, hotkeys and other out-of-band triggers."""

    def __init__(self) -> None:
        self._activations: asyncio.Queue[Activation] = asyncio.Queue()

    async def activate(self, *, speech_start_timeout: float | None = None) -> None:
        """Request a turn that starts at live audio rather than at past history."""
        await self._activations.put(
            Activation(speech_start_timeout=speech_start_timeout)
        )

    async def activations(self) -> AsyncIterator[Activation]:
        while True:
            yield await self._activations.get()
