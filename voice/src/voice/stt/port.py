from abc import ABC, abstractmethod
from collections.abc import AsyncIterable, AsyncIterator
from dataclasses import dataclass


@dataclass(frozen=True)
class Transcription:
    text: str
    is_final: bool


class SpeechToText(ABC):
    """Streams audio into provider-independent transcription updates."""

    @abstractmethod
    def transcribe(
        self, audio: AsyncIterable[bytes]
    ) -> AsyncIterator[Transcription]: ...
