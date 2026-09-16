from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, TypeAdapter

from gateway.features.voice.application import VoiceEventType
from gateway.features.voice.domain import Activation
from gateway.presentation.models import ApiModel


class VoiceRpcMethod(StrEnum):
    TURN_START = "voice.turn.start"
    TURN_INTERRUPT = "voice.turn.interrupt"
    TURN_PLAYBACK_COMPLETED = "voice.turn.playback_completed"


class VoiceNotificationMethod(StrEnum):
    VOICE_EVENT = "voice.event"


class StartVoiceTurnParams(ApiModel):
    voice_session_id: UUID
    activation: Activation
    pre_roll_sequence: int | None = Field(default=None, ge=0)


class VoiceTurnParams(ApiModel):
    voice_turn_id: UUID


class InterruptVoiceTurnParams(VoiceTurnParams):
    input_sequence: int | None = Field(default=None, ge=0)


class VoiceTurnCommandResult(ApiModel):
    voice_session_id: UUID
    voice_turn_id: UUID


class VoiceEventBase(ApiModel):
    event_id: UUID
    timestamp: datetime
    voice_session_id: UUID
    voice_turn_id: UUID
    session_id: UUID
    sequence: int


class VoiceConversationStarted(ApiModel):
    type: Literal[VoiceEventType.CONVERSATION_STARTED]
    event_id: UUID
    timestamp: datetime
    voice_session_id: UUID
    session_id: UUID
    sequence: int


class VoiceConversationInactivityCountdown(ApiModel):
    type: Literal[VoiceEventType.CONVERSATION_INACTIVITY_COUNTDOWN]
    event_id: UUID
    timestamp: datetime
    voice_session_id: UUID
    session_id: UUID
    sequence: int
    remaining_seconds: int


class VoiceConversationEnded(ApiModel):
    type: Literal[VoiceEventType.CONVERSATION_ENDED]
    event_id: UUID
    timestamp: datetime
    voice_session_id: UUID
    session_id: UUID
    sequence: int
    reason: str


class VoiceTurnStarted(VoiceEventBase):
    type: Literal[VoiceEventType.TURN_STARTED]
    activation: Activation


class VoiceTranscriptFinal(VoiceEventBase):
    type: Literal[VoiceEventType.TRANSCRIPT_FINAL]
    text: str
    user_message_id: UUID


class VoiceAssistantTextStarted(VoiceEventBase):
    type: Literal[VoiceEventType.ASSISTANT_TEXT_STARTED]


class VoiceAssistantToolStarted(VoiceEventBase):
    type: Literal[VoiceEventType.ASSISTANT_TOOL_STARTED]
    name: str


class VoiceAssistantToolCompleted(VoiceEventBase):
    type: Literal[VoiceEventType.ASSISTANT_TOOL_COMPLETED]
    name: str


class VoiceAssistantAudioStarted(VoiceEventBase):
    type: Literal[VoiceEventType.ASSISTANT_AUDIO_STARTED]


class VoiceAssistantAudioCompleted(VoiceEventBase):
    type: Literal[VoiceEventType.ASSISTANT_AUDIO_COMPLETED]


class VoiceTurnCompleted(VoiceEventBase):
    type: Literal[VoiceEventType.TURN_COMPLETED]


class VoiceTurnDiscarded(VoiceEventBase):
    type: Literal[VoiceEventType.TURN_DISCARDED]


class VoiceTurnCancelled(VoiceEventBase):
    type: Literal[VoiceEventType.TURN_CANCELLED]
    reason: str


class VoiceTurnFailed(VoiceEventBase):
    type: Literal[VoiceEventType.TURN_FAILED]
    code: str
    message: str


class VoiceTranscriptPartial(ApiModel):
    type: Literal[VoiceEventType.TRANSCRIPT_PARTIAL]
    event_id: UUID
    timestamp: datetime
    voice_session_id: UUID
    voice_turn_id: UUID
    session_id: UUID
    revision: int
    text: str


class VoiceSessionClosed(ApiModel):
    type: Literal[VoiceEventType.SESSION_CLOSED]
    event_id: UUID
    timestamp: datetime
    voice_session_id: UUID
    session_id: UUID
    sequence: int
    reason: str


type VoiceEventMessage = Annotated[
    VoiceConversationStarted
    | VoiceConversationInactivityCountdown
    | VoiceConversationEnded
    | VoiceTurnStarted
    | VoiceTranscriptPartial
    | VoiceTranscriptFinal
    | VoiceAssistantTextStarted
    | VoiceAssistantToolStarted
    | VoiceAssistantToolCompleted
    | VoiceAssistantAudioStarted
    | VoiceAssistantAudioCompleted
    | VoiceTurnCompleted
    | VoiceTurnDiscarded
    | VoiceTurnCancelled
    | VoiceTurnFailed
    | VoiceSessionClosed,
    Field(discriminator="type"),
]

VOICE_EVENT_ADAPTER: TypeAdapter[VoiceEventMessage] = TypeAdapter(VoiceEventMessage)
