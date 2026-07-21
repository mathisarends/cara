import asyncio
from typing import Self

from cara.wakeword.ports import WakeWordDetectionSource


class BargeInCapture:
    """Listens for an explicit wake word during one assistant response."""

    def __init__(self, wake_word_listener: WakeWordDetectionSource) -> None:
        self._wake_word_listener = wake_word_listener
        self._interrupt = asyncio.Event()
        self._cancel = asyncio.Event()
        self._listening: asyncio.Task[None] | None = None

    @property
    def interrupt(self) -> asyncio.Event:
        return self._interrupt

    async def __aenter__(self) -> Self:
        if self._listening is not None:
            raise RuntimeError("Barge-in capture is already running.")
        self._listening = asyncio.create_task(self._listen())
        return self

    async def __aexit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self._cancel.set()
        if self._listening is not None:
            await self._listening

    async def _listen(self) -> None:
        score = await self._wake_word_listener.detect_once(cancel=self._cancel)
        if score is not None:
            self._interrupt.set()
