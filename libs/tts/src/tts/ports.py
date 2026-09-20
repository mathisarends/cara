from abc import ABC, abstractmethod
from collections.abc import AsyncIterable, AsyncIterator


class StreamingTextToSpeech[ConfigT](ABC):
    @abstractmethod
    def stream(
        self, text: str, *, config: ConfigT | None = None
    ) -> AsyncIterator[bytes]: ...

    @abstractmethod
    def stream_incremental(
        self, text: AsyncIterable[str], *, config: ConfigT | None = None
    ) -> AsyncIterator[bytes]: ...
