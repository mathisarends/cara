"""Cara package."""

from cara.assistant import VoiceAssistant, VoiceSession, VoiceTurn
from cara.conversation import Conversation
from cara.events import BaseEvent, EventBus, EventHandler
from cara.listener.hue import HueLifecycleListener
from cara.listener import LifecycleListener, ListenerRegistry
from cara.lifecycle import (
    AnswerGenerated,
    AssistantEvent,
    AssistantState,
    LoggingLifecycleListener,
    SessionEnded,
    SessionStarted,
    StateChanged,
    Transcribed,
    TurnCompleted,
    TurnStarted,
)
from cara.sonos import SonosAudioPlayer
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
    "AssistantState",
    "AsyncOpenAISpeechToText",
    "AsyncOpenAITextToSpeech",
    "BaseEvent",
    "Conversation",
    "EventBus",
    "EventHandler",
    "HueLifecycleListener",
    "LifecycleListener",
    "ListenerRegistry",
    "LoggingLifecycleListener",
    "SessionEnded",
    "SessionStarted",
    "SonosAudioPlayer",
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
    "VoiceSession",
    "VoiceTurn",
    "text_to_speech",
    "transcribe_audio",
]
