from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class SessionStarted:
    pass


@dataclass(frozen=True, slots=True)
class SessionStopped:
    pass


@dataclass(frozen=True, slots=True)
class WakeWordDetected:
    name: str
    score: float
    sequence: int


@dataclass(frozen=True, slots=True)
class UserTurnStarted:
    """The microphone is open for the user's part of a turn."""

    turn_id: UUID


@dataclass(frozen=True, slots=True)
class UserSpeechStarted:
    """The backend heard the user speak, as opposed to an open microphone."""

    turn_id: UUID


@dataclass(frozen=True, slots=True)
class UserSpeechEnded:
    turn_id: UUID


@dataclass(frozen=True, slots=True)
class AssistantTurnStarted:
    """The assistant is working on its response to the turn."""

    turn_id: UUID


@dataclass(frozen=True, slots=True)
class AssistantTextStarted:
    turn_id: UUID


@dataclass(frozen=True, slots=True)
class AssistantToolStarted:
    turn_id: UUID
    name: str


@dataclass(frozen=True, slots=True)
class AssistantToolCompleted:
    turn_id: UUID
    name: str


@dataclass(frozen=True, slots=True)
class AssistantSpeechStarted:
    """The first chunk of the assistant's response reached the output."""

    turn_id: UUID


@dataclass(frozen=True, slots=True)
class AssistantSpeechCompleted:
    """The output played the assistant's complete response."""

    turn_id: UUID


@dataclass(frozen=True, slots=True)
class VoiceTurnInterrupted:
    turn_id: UUID


@dataclass(frozen=True, slots=True)
class VoiceTurnTimedOut:
    turn_id: UUID


@dataclass(frozen=True, slots=True)
class VoiceTurnFailed:
    turn_id: UUID
    message: str


@dataclass(frozen=True, slots=True)
class VoiceTurnEnded:
    turn_id: UUID


@dataclass(frozen=True, slots=True)
class VoiceConversationStarted:
    pass


@dataclass(frozen=True, slots=True)
class VoiceConversationInactivityCountdown:
    remaining_seconds: int


@dataclass(frozen=True, slots=True)
class VoiceConversationEnded:
    reason: str


type VoiceLifecycleEvent = (
    SessionStarted
    | SessionStopped
    | WakeWordDetected
    | UserTurnStarted
    | UserSpeechStarted
    | UserSpeechEnded
    | AssistantTurnStarted
    | AssistantTextStarted
    | AssistantToolStarted
    | AssistantToolCompleted
    | AssistantSpeechStarted
    | AssistantSpeechCompleted
    | VoiceTurnInterrupted
    | VoiceTurnTimedOut
    | VoiceTurnFailed
    | VoiceTurnEnded
    | VoiceConversationStarted
    | VoiceConversationInactivityCountdown
    | VoiceConversationEnded
)
