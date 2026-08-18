from abc import ABC, abstractmethod
from collections.abc import AsyncIterable, AsyncIterator

from voice.transcription import Transcription


class SpeechToText(ABC):
    """Streams audio into provider-independent transcription updates."""

    @abstractmethod
    def transcribe(
        self, audio: AsyncIterable[bytes]
    ) -> AsyncIterator[Transcription]: ...

    async def aclose(self) -> None:  # noqa: B027 - optional provider hook
        """Release provider resources owned by this speech-to-text client."""
