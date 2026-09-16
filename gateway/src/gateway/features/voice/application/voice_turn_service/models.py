import asyncio
from collections.abc import AsyncIterator
from enum import Enum, auto


class Flush(Enum):
    MARKER = auto()


type SpeechQueue = asyncio.Queue[str | Flush | None]


class SpeechSegments:
    """Splits a turn's text stream at flush markers so text spoken before a
    tool call is synthesized right away instead of at the end of the turn."""

    def __init__(self, queue: SpeechQueue) -> None:
        self._queue = queue
        self._ended = False

    async def next(self) -> AsyncIterator[str] | None:
        while not self._ended:
            item = await self._queue.get()
            if item is None:
                self._ended = True
            elif isinstance(item, str) and item.strip():
                return self._rest(item)
        return None

    async def _rest(self, first: str) -> AsyncIterator[str]:
        yield first
        while True:
            item = await self._queue.get()
            if item is None:
                self._ended = True
                return
            if item is Flush.MARKER:
                return
            yield item
