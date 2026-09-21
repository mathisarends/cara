from contextlib import AsyncExitStack
from types import TracebackType
from typing import Self

from voice.runtime import VoiceRuntime


class VoiceSession:
    """A fully constructed, one-shot local voice session."""

    def __init__(
        self,
        *,
        runtime: VoiceRuntime,
        resources: AsyncExitStack,
    ) -> None:
        self._runtime = runtime
        # The only owner of external resources such as the backend connection
        # and audio devices; the runtime merely uses them.
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
            await self._runtime.run()
        finally:
            await self.close()

    async def wait_started(self) -> None:
        if self._closed:
            raise RuntimeError("Voice session is closed.")
        await self._runtime.wait_started()

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        resources, self._resources = self._resources, None
        try:
            await self._runtime.stop()
        finally:
            if resources is not None:
                await resources.aclose()
