from transitbus import Event

from voice.stt import TranscriptionKind


class WakeWordDetected(Event):
    """Emitted when the configured wake word is detected."""

    score: float
    sequence: int
    name: str


class VoiceTurnRequested(Event):
    """Requests a voice turn starting at an audio-hub sequence."""

    sequence: int


class VoiceInterruptionRequested(Event):
    """Requests cancellation of the currently active voice turn, if any."""


class VoiceTurnEnded(Event):
    """Emitted whenever a requested voice turn releases its resources."""

    turn_id: int


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
