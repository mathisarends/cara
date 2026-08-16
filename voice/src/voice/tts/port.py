from abc import ABC, abstractmethod
from collections.abc import AsyncIterable, AsyncIterator


class TextToSpeech(ABC):
    """Streams text into provider-independent encoded audio chunks."""

    @abstractmethod
    def synthesize(self, text: AsyncIterable[str]) -> AsyncIterator[bytes]: ...
