"""OpenAI speech wrappers."""

from .models import (
    SpeechToTextRequest,
    SpeechToTextResponse,
    TextToSpeechFormat,
    TextToSpeechRequest,
    TextToSpeechResponse,
)
from .ports import SpeechToText, TextToSpeech
from .stt import OpenAISpeechToText
from .tts import OpenAITextToSpeech

__all__ = [
    "OpenAISpeechToText",
    "OpenAITextToSpeech",
    "SpeechToText",
    "SpeechToTextRequest",
    "SpeechToTextResponse",
    "TextToSpeech",
    "TextToSpeechFormat",
    "TextToSpeechRequest",
    "TextToSpeechResponse",
]
