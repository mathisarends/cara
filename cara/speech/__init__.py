"""OpenAI speech wrappers."""

from cara.speech.models import (
    SpeechToTextRequest,
    SpeechToTextResponse,
    TextToSpeechFormat,
    TextToSpeechRequest,
    TextToSpeechResponse,
)
from cara.speech.stt import AsyncOpenAISpeechToText, transcribe_audio
from cara.speech.tts import AsyncOpenAITextToSpeech, text_to_speech

__all__ = [
    "AsyncOpenAISpeechToText",
    "AsyncOpenAITextToSpeech",
    "SpeechToTextRequest",
    "SpeechToTextResponse",
    "TextToSpeechFormat",
    "TextToSpeechRequest",
    "TextToSpeechResponse",
    "text_to_speech",
    "transcribe_audio",
]
