from abc import ABC, abstractmethod

from cara.speech.models import SpeechToTextRequest, SpeechToTextResponse, TextToSpeechRequest, TextToSpeechResponse


class SpeechToText(ABC):
    """Transcribes spoken audio into text."""

    @abstractmethod
    async def transcribe(self, request: SpeechToTextRequest) -> SpeechToTextResponse:
        """Transcribe the given audio."""


class TextToSpeech(ABC):
    """Synthesizes spoken audio from text."""

    @abstractmethod
    async def synthesize(self, request: TextToSpeechRequest) -> TextToSpeechResponse:
        """Synthesize audio for the given text."""
