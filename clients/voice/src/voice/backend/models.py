from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

from voice.activation import ActivationKind
from voice.audio.models import AudioFormat


@dataclass(frozen=True, slots=True)
class TurnRef:
    id: UUID


class TurnPhase(StrEnum):
    LISTENING = "listening"
    TRANSCRIBING = "transcribing"
    WAITING_FOR_ASSISTANT = "waiting_for_assistant"
    SPEAKING = "speaking"


@dataclass(frozen=True, slots=True)
class ActiveTurn:
    turn: TurnRef
    phase: TurnPhase


@dataclass(frozen=True, slots=True)
class BackendSessionState:
    """What the backend already knows about the session when it connects."""

    active_turn: ActiveTurn | None = None


@dataclass(frozen=True, slots=True)
class BackendConnectionOptions:
    room: str
    channel: str
    inactivity_timeout_seconds: float
    input_format: AudioFormat
    output_format: AudioFormat


@dataclass(frozen=True, slots=True)
class StartTurn:
    activation: ActivationKind
    # Where the turn's input begins in the captured audio; ``None`` starts at
    # live audio.
    pre_roll_sequence: int | None = None


@dataclass(frozen=True, slots=True)
class StartedTurn:
    turn: TurnRef


@dataclass(frozen=True, slots=True)
class ConversationStarted:
    pass


@dataclass(frozen=True, slots=True)
class ConversationCountdown:
    remaining_seconds: int


@dataclass(frozen=True, slots=True)
class ConversationEnded:
    reason: str


@dataclass(frozen=True, slots=True)
class TurnStarted:
    """A turn the backend started itself, or confirms after ``start_turn``."""

    turn: TurnRef
    # A proactive turn delivers assistant output without listening first.
    proactive: bool = False


@dataclass(frozen=True, slots=True)
class TranscriptUpdated:
    """The backend heard speech in the turn's input."""

    turn: TurnRef


@dataclass(frozen=True, slots=True)
class TranscriptCompleted:
    """The user's part of the turn is over; the assistant takes it from here."""

    turn: TurnRef


@dataclass(frozen=True, slots=True)
class AssistantTextStarted:
    turn: TurnRef


@dataclass(frozen=True, slots=True)
class AssistantToolStarted:
    turn: TurnRef
    name: str


@dataclass(frozen=True, slots=True)
class AssistantToolCompleted:
    turn: TurnRef
    name: str


@dataclass(frozen=True, slots=True)
class TurnCompleted:
    """The turn ended normally or was cancelled."""

    turn: TurnRef


@dataclass(frozen=True, slots=True)
class TurnDiscarded:
    """The turn ended because the user never said anything."""

    turn: TurnRef


@dataclass(frozen=True, slots=True)
class TurnFailed:
    turn: TurnRef
    message: str


@dataclass(frozen=True, slots=True)
class SessionClosed:
    reason: str


type BackendEvent = (
    ConversationStarted
    | ConversationCountdown
    | ConversationEnded
    | TurnStarted
    | TranscriptUpdated
    | TranscriptCompleted
    | AssistantTextStarted
    | AssistantToolStarted
    | AssistantToolCompleted
    | TurnCompleted
    | TurnDiscarded
    | TurnFailed
    | SessionClosed
)


@dataclass(frozen=True, slots=True)
class BackendAudioFrame:
    turn: TurnRef
    pcm: bytes


@dataclass(frozen=True, slots=True)
class BackendAudioEnd:
    """The backend has produced all audio of the turn's response."""

    turn: TurnRef


type BackendAudio = BackendAudioFrame | BackendAudioEnd
