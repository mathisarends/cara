from abc import ABC, abstractmethod
from collections.abc import AsyncIterable, AsyncIterator


class StreamingSpeechToText[ConfigT, EventT](ABC):
    @abstractmethod
    def stream(
        self,
        audio: AsyncIterable[bytes],
        *,
        config: ConfigT | None = None,
    ) -> AsyncIterator[EventT]: ...
