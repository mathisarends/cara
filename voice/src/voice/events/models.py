from pydantic import BaseModel, ConfigDict

from voice.stt import TranscriptionKind


class Event(BaseModel):
    model_config = ConfigDict(extra="forbid")


class WakeWordDetected(Event):
    """Emitted when the configured wake word is detected."""

    score: float
    sequence: int
    name: str


class VoiceTurnRequested(Event):
    """Requests a voice turn; without a sequence it starts at live audio."""

    sequence: int | None = None
    speech_start_timeout: float | None = None


class VoiceInterruptionRequested(Event):
    """Requests cancellation of the currently active voice turn, if any."""


class VoiceResourcesClosing(Event):
    """Requests release of resources after session-end handlers have finished."""


class VoiceTurnEnded(Event):
    """Emitted whenever a requested voice turn releases its resources."""

    turn_id: int


class VoiceTurnTimedOut(Event):
    turn_id: int


class VoiceTurnFailed(Event):
    turn_id: int
    message: str


class FollowUpCountdown(Event):
    """Emitted once per remaining second while a follow-up window runs out."""

    remaining_seconds: int


class FollowUpTimedOut(Event):
    """Emitted when a follow-up window closes without the user speaking."""

    timeout_seconds: float


class UserTranscriptionUpdated(Event):
    turn_id: int
    text: str
    is_final: bool
    kind: TranscriptionKind


class UserAudioChunk(Event):
    turn_id: int
    chunk: bytes


class AssistantResponseStarted(Event):
    turn_id: int


class AssistantTextChunk(Event):
    turn_id: int
    chunk: str


class AssistantTextCompleted(Event):
    turn_id: int


class AssistantAudioStarted(Event):
    """Declares the format of the PCM stream produced for one response."""

    turn_id: int
    sample_rate: int
    channels: int = 1


class AssistantAudioChunk(Event):
    turn_id: int
    chunk: bytes


class AssistantAudioCompleted(Event):
    """Emitted when TTS has finished producing PCM for a response."""

    turn_id: int


class AssistantPlaybackCompleted(Event):
    """Emitted after the produced PCM has reached the audio output."""

    turn_id: int


class AudioPlaybackRequested(Event):
    """Requests playback of a complete WAV clip on the shared audio output."""

    audio: bytes
