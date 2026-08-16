from abc import ABC, abstractmethod
from collections.abc import AsyncIterable, AsyncIterator


class TextToSpeech(ABC):
    """Streams text into provider-independent encoded audio chunks."""

    @abstractmethod
    def synthesize(self, text: AsyncIterable[str]) -> AsyncIterator[bytes]: ...

    async def aclose(self) -> None:  # noqa: B027 - optional provider hook
        """Release provider resources owned by this text-to-speech client."""
