from .assistant import VoiceAssistant
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
    TurnStarted,
)
from .listener import LifecycleListener, ListenerRegistry
from .listener.lights import HueLifecycleListener
from .messages import MessageManager, SystemPrompt
from .speech import (
    OpenAISpeechToText,
    OpenAITextToSpeech,
    SpeechToTextRequest,
    SpeechToTextResponse,
    TextToSpeechFormat,
    TextToSpeechRequest,
    TextToSpeechResponse,
)
from .views import SpeechConfig

__all__ = [
    "AnswerGenerated",
    "AssistantState",
    "OpenAISpeechToText",
    "OpenAITextToSpeech",
    "Event",
    "EventBus",
    "EventHandler",
    "HueLifecycleListener",
    "LifecycleListener",
    "ListenerRegistry",
    "MessageManager",
    "SessionEnded",
    "SessionStarted",
    "SonosAudioPlayer",
    "SpeechConfig",
    "SpeechToTextRequest",
    "SpeechToTextResponse",
    "StateChanged",
    "SystemPrompt",
    "TextToSpeechFormat",
    "TextToSpeechRequest",
    "TextToSpeechResponse",
    "Transcribed",
    "TurnStarted",
    "VoiceAssistant",
]


def __getattr__(name: str) -> object:
    if name == "SonosAudioPlayer":
        from .audio import SonosAudioPlayer

        return SonosAudioPlayer
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
