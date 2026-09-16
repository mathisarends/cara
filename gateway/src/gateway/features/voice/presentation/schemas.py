from datetime import datetime
from uuid import UUID

from pydantic import Field

from gateway.features.voice.domain import (
    Activation,
    AudioEncoding,
    VoiceSessionStatus,
    VoiceTurnStatus,
)
from gateway.presentation.models import ApiModel


class AudioFormat(ApiModel):
    encoding: AudioEncoding
    sample_rate: int = Field(gt=0)
    channels: int = Field(ge=1)


class OpenVoiceSessionRequest(ApiModel):
    session_id: UUID
    room: str = Field(min_length=1, pattern=r"\S")
    input_formats: tuple[AudioFormat, ...] = Field(min_length=1)
    output_formats: tuple[AudioFormat, ...] = Field(min_length=1)


class VoiceSessionResponse(ApiModel):
    id: UUID
    session_id: UUID
    room: str
    status: VoiceSessionStatus
    input_format: AudioFormat
    output_format: AudioFormat
    media_path: str
    media_connected: bool
    created_at: datetime
    closed_at: datetime | None
    close_reason: str | None


class VoiceTurnResponse(ApiModel):
    id: UUID
    index: int
    activation: Activation
    status: VoiceTurnStatus
    transcript: str | None
    user_message_id: UUID | None
    error: str | None
    started_at: datetime
    input_ended_at: datetime | None
    transcribed_at: datetime | None
    speech_started_at: datetime | None
    ended_at: datetime | None


class VoiceSessionListResponse(ApiModel):
    voice_sessions: tuple[VoiceSessionResponse, ...]


class VoiceSessionSnapshotResponse(ApiModel):
    voice_session: VoiceSessionResponse
    turns: tuple[VoiceTurnResponse, ...]
    active_turn_id: UUID | None
    last_sequence: int
