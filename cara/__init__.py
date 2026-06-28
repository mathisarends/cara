"""Cara package."""

from cara.assistant import VoiceAssistant, VoiceTurn
from cara.lifecycle import (
    AnswerGenerated,
    AssistantEvent,
    AssistantLifecycleListener,
    AssistantState,
    LoggingLifecycleListener,
    StateChanged,
    Transcribed,
    TurnCompleted,
    TurnStarted,
)
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
    "AnswerGenerated",
    "AssistantEvent",
    "AssistantLifecycleListener",
    "AssistantState",
    "AsyncOpenAISpeechToText",
    "AsyncOpenAITextToSpeech",
    "LoggingLifecycleListener",
    "SpeechToTextRequest",
    "SpeechToTextResponse",
    "StateChanged",
    "TextToSpeechFormat",
    "TextToSpeechRequest",
    "TextToSpeechResponse",
    "Transcribed",
    "TurnCompleted",
    "TurnStarted",
    "VoiceAssistant",
    "VoiceTurn",
    "text_to_speech",
    "transcribe_audio",
]
