from .assistant import VoiceAssistant, VoiceSession, VoiceTurn
from .conversation import Conversation
from .events import (
    AnswerGenerated,
    AssistantState,
    Event,
    EventBus,
    EventHandler,
    SessionEnded,
    SessionStarted,
    StateChanged,
    Transcribed,
    TurnCompleted,
    TurnStarted,
)
from .listener import LifecycleListener, ListenerRegistry
from .listener.lights import HueLifecycleListener
from .speech import (
    OpenAISpeechToText,
    OpenAITextToSpeech,
    SpeechToTextRequest,
    SpeechToTextResponse,
    TextToSpeechFormat,
    TextToSpeechRequest,
    TextToSpeechResponse,
)

__all__ = [
    "AnswerGenerated",
    "AssistantState",
    "OpenAISpeechToText",
    "OpenAITextToSpeech",
    "Event",
    "Conversation",
    "EventBus",
    "EventHandler",
    "HueLifecycleListener",
    "LifecycleListener",
    "ListenerRegistry",
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
]


def __getattr__(name: str) -> object:
    if name == "SonosAudioPlayer":
        from .audio import SonosAudioPlayer

        return SonosAudioPlayer
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
