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
    "TextToSpeechVoice",
]
