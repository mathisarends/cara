from contextlib import AsyncExitStack
from types import TracebackType
from typing import Self

from voice.channel import VoiceChannel


class VoiceSession:
    """A fully constructed, one-shot local voice session."""

    def __init__(
        self,
        *,
        channel: VoiceChannel,
        resources: AsyncExitStack,
    ) -> None:
        self._channel = channel
        self._resources: AsyncExitStack | None = resources
        self._closed = False

    async def __aenter__(self) -> Self:
        if self._closed:
            raise RuntimeError("Voice session is closed.")
        return self

    async def __aexit__(
        self,
        _exc_type: type[BaseException] | None,
        _exc_value: BaseException | None,
        _traceback: TracebackType | None,
    ) -> None:
        await self.close()

    async def run(self) -> None:
        if self._closed:
            raise RuntimeError("Voice session is closed.")
        try:
            await self._channel.start()
        finally:
            await self.close()

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        resources, self._resources = self._resources, None
        try:
            await self._channel.stop()
        finally:
            if resources is not None:
                await resources.aclose()
