from uuid import UUID

from pydantic import BaseModel, ConfigDict

from voice.activation_kind import ActivationKind
from voice.transcription import TranscriptionKind


class Event(BaseModel):
    """A lifecycle fact, broadcast to every interested listener."""

    model_config = ConfigDict(extra="forbid")


class Request(BaseModel):
    """A unit of work for exactly one handler, whose failures reach the caller."""

    model_config = ConfigDict(extra="forbid")


class SessionStarted(Event):
    """Emitted when a voice session begins."""


class UserTurnStarted(Event):
    """Emitted when the voice channel starts waiting for the user."""


class AssistantTurnStarted(Event):
    """Emitted when the model starts working on a user turn."""


class UserSpeechStarted(Event):
    """Emitted when voice activity is first detected for a user utterance."""


class UserSpeechEnded(Event):
    """Emitted when the recorder accepts the end of a user utterance."""


class AssistantSpeechStarted(Event):
    """Emitted immediately before the first assistant audio chunk is played."""


class SessionEnded(Event):
    """Emitted when a voice session ends."""


class VoiceConversationStarted(Event):
    """Emitted when the gateway starts an active voice conversation."""


class VoiceConversationInactivityCountdown(Event):
    """Emitted while the gateway waits for another user utterance."""

    remaining_seconds: int


class VoiceConversationEnded(Event):
    """Emitted when the gateway ends the active voice conversation."""

    reason: str


class WakeWordDetected(Event):
    """Emitted when the configured wake word is detected."""

    score: float
    sequence: int
    name: str


class VoiceTurnRequested(Request):
    """Requests a voice turn; without a sequence it starts at live audio."""

    sequence: int | None = None
    speech_start_timeout: float | None = None
    activation: ActivationKind = ActivationKind.MANUAL


class VoiceResourcesClosing(Event):
    """Requests release of resources after session-end handlers have finished."""


class VoiceTurnStarted(Event):
    """Emitted when a voice turn is claimed, whatever kind of input drives it."""

    turn_id: UUID


class VoiceTurnEnded(Event):
    """Emitted whenever a requested voice turn releases its resources."""

    turn_id: UUID


class VoiceTurnInterrupted(Event):
    """Emitted when the user takes the floor before the turn finished."""

    turn_id: UUID


class VoiceTurnTimedOut(Event):
    turn_id: UUID


class VoiceTurnFailed(Event):
    turn_id: UUID
    message: str


class UserTranscriptionUpdated(Event):
    turn_id: UUID
    text: str
    is_final: bool
    kind: TranscriptionKind


class UserTranscriptionCompleted(Event):
    turn_id: UUID
    text: str


class UserAudioChunk(Event):
    """A continuously captured microphone frame, independent of voice turns."""

    sequence: int
    chunk: bytes


class AssistantResponseStarted(Event):
    turn_id: UUID


class AssistantTextChunk(Event):
    turn_id: UUID
    chunk: str


class AssistantTextCompleted(Event):
    turn_id: UUID
    text: str


class AssistantToolStarted(Event):
    turn_id: UUID
    name: str


class AssistantToolCompleted(Event):
    turn_id: UUID
    name: str


class AssistantAudioStarted(Event):
    """Declares the format of the PCM stream produced for one response."""

    turn_id: UUID
    sample_rate: int
    channels: int = 1


class AssistantAudioChunk(Event):
    turn_id: UUID
    chunk: bytes


class AssistantAudioCompleted(Event):
    """Emitted when TTS has finished producing PCM for a response."""

    turn_id: UUID


class AssistantPlaybackCompleted(Event):
    """Emitted after the produced PCM has reached the audio output."""

    turn_id: UUID


class AudioPlaybackRequested(Request):
    """Requests playback of a complete WAV clip on the shared audio output."""

    audio: bytes
