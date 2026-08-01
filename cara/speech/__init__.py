"""Speech interfaces backed by the vocalbin library."""

from vocalbin import (
    OpenAISpeechToText,
    OpenAITextToSpeech,
    SpeechToText,
    SpeechToTextRequest,
    SpeechToTextResponse,
    TextToSpeech,
    TextToSpeechFormat,
    TextToSpeechRequest,
    TextToSpeechResponse,
    TextToSpeechVoice,
)

from .input import SpeechInput
from .output import SpeechOutput
from .settings import SpeechSettings

__all__ = [
    "OpenAISpeechToText",
    "OpenAITextToSpeech",
    "SpeechToText",
    "SpeechToTextRequest",
    "SpeechToTextResponse",
    "SpeechInput",
    "SpeechOutput",
    "SpeechSettings",
    "TextToSpeech",
    "TextToSpeechFormat",
    "TextToSpeechRequest",
    "TextToSpeechResponse",
    "TextToSpeechVoice",
]
