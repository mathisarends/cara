from abc import ABC, abstractmethod
from collections.abc import AsyncIterable, AsyncIterator


class StreamingTextToSpeech[ConfigT](ABC):
    async def warmup(self) -> None:
        """Prepares the next stream for low latency, for example by opening a
        connection or loading a model. Idempotent, and never a precondition:
        streaming stays correct without it and after a warmup went stale."""
        return None

    @abstractmethod
    def stream(
        self, text: str, *, config: ConfigT | None = None
    ) -> AsyncIterator[bytes]: ...

    @abstractmethod
    def stream_incremental(
        self, text: AsyncIterable[str], *, config: ConfigT | None = None
    ) -> AsyncIterator[bytes]: ...

    @abstractmethod
    async def aclose(self) -> None: ...
