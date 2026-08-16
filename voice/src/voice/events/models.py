from transitbus import Event

from voice.stt import TranscriptionKind


class WakeWordDetected(Event):
    """Emitted when the configured wake word is detected."""

    score: float
    sequence: int
    name: str


class VoiceTurnTimedOut(Event):
    turn_id: int


class VoiceTurnFailed(Event):
    turn_id: int
    message: str


class UserTranscriptionUpdated(Event):
    turn_id: int
    text: str
    is_final: bool
    kind: TranscriptionKind


class AssistantResponseStarted(Event):
    turn_id: int


class AssistantTextChunk(Event):
    turn_id: int
    chunk: str


class AssistantTextCompleted(Event):
    turn_id: int


class AssistantAudioChunk(Event):
    turn_id: int
    chunk: bytes


class AssistantAudioCompleted(Event):
    turn_id: int
