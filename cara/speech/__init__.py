"""OpenAI speech wrappers."""

from .models import (
    SpeechToTextRequest,
    SpeechToTextResponse,
    TextToSpeechFormat,
    TextToSpeechRequest,
    TextToSpeechResponse,
)
from .stt import OpenAISpeechToText
from .tts import OpenAITextToSpeech

__all__ = [
    "OpenAISpeechToText",
    "OpenAITextToSpeech",
    "SpeechToTextRequest",
    "SpeechToTextResponse",
    "TextToSpeechFormat",
    "TextToSpeechRequest",
    "TextToSpeechResponse",
]
