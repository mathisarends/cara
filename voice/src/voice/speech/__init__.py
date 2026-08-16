"""Speech services and text/audio input-output adapters."""

from vocalbin.openai import (
    SpeechToText,
    SpeechToTextConfig,
    SpeechToTextResponse,
    TextToSpeech,
    TextToSpeechConfig,
    TextToSpeechFormat,
    TextToSpeechResponse,
    TextToSpeechVoice,
)

from .input import SpeechInput
from .output import SpeechOutput
from .settings import SpeechSettings

__all__ = [
    "SpeechToText",
    "SpeechToTextConfig",
    "SpeechToTextResponse",
    "SpeechInput",
    "SpeechOutput",
    "SpeechSettings",
    "TextToSpeech",
    "TextToSpeechConfig",
    "TextToSpeechFormat",
    "TextToSpeechResponse",
    "TextToSpeechVoice",
]
