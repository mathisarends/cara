from pydantic import BaseModel, ConfigDict

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


class WakeWordDetected(Event):
    """Emitted when the configured wake word is detected."""

    score: float
    sequence: int
    name: str


class VoiceTurnRequested(Request):
    """Requests a voice turn; without a sequence it starts at live audio."""

    sequence: int | None = None
    speech_start_timeout: float | None = None


class PromptTurnRequested(Request):
    """Requests a voice turn on given text, bypassing the user's microphone."""

    prompt: str


class VoiceResourcesClosing(Event):
    """Requests release of resources after session-end handlers have finished."""


class VoiceTurnStarted(Event):
    """Emitted when a voice turn is claimed, whatever kind of input drives it."""

    turn_id: int


class VoiceTurnEnded(Event):
    """Emitted whenever a requested voice turn releases its resources."""

    turn_id: int


class VoiceTurnInterrupted(Event):
    """Emitted when the user takes the floor before the turn finished."""

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


class UserTranscriptionCompleted(Event):
    turn_id: int
    text: str


class UserTranscriptionRequested(Request):
    """Requests turn-scoped STT from the continuously captured audio history."""

    turn_id: int
    sequence: int | None = None
    pre_roll_seconds: float = 0.0
    speech_start_timeout: float


class UserAudioChunk(Event):
    """A continuously captured microphone frame, independent of voice turns."""

    sequence: int
    chunk: bytes


class AssistantResponseStarted(Event):
    turn_id: int


class AssistantResponseRequested(Request):
    turn_id: int
    text: str


class AssistantTextChunk(Event):
    turn_id: int
    chunk: str


class AssistantTextCompleted(Event):
    turn_id: int
    text: str


class AssistantToolStarted(Event):
    turn_id: int
    name: str


class AssistantToolCompleted(Event):
    turn_id: int
    name: str


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


class AudioPlaybackRequested(Request):
    """Requests playback of a complete WAV clip on the shared audio output."""

    audio: bytes
