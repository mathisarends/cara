"""Cara package."""

from cara.assistant import AssistantConfig, AsyncOpenAIChat, VoiceAssistant, VoiceTurn
from cara.speech import (
    AsyncOpenAISpeechToText,
    AsyncOpenAITextToSpeech,
    SpeechToTextRequest,
    SpeechToTextResponse,
    TextToSpeechFormat,
    TextToSpeechRequest,
    TextToSpeechResponse,
    text_to_speech,
    transcribe_audio,
)

__all__ = [
    "AssistantConfig",
    "AsyncOpenAIChat",
    "AsyncOpenAISpeechToText",
    "AsyncOpenAITextToSpeech",
    "SpeechToTextRequest",
    "SpeechToTextResponse",
    "TextToSpeechFormat",
    "TextToSpeechRequest",
    "TextToSpeechResponse",
    "VoiceAssistant",
    "VoiceTurn",
    "text_to_speech",
    "transcribe_audio",
]
