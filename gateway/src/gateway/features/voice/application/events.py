import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID


class VoiceEventType(StrEnum):
    TURN_STARTED = "voice.turn.started"
    TRANSCRIPT_PARTIAL = "voice.transcript.partial"
    TRANSCRIPT_FINAL = "voice.transcript.final"
    ASSISTANT_AUDIO_STARTED = "voice.assistant_audio.started"
    ASSISTANT_AUDIO_COMPLETED = "voice.assistant_audio.completed"
    TURN_COMPLETED = "voice.turn.completed"
    TURN_DISCARDED = "voice.turn.discarded"
    TURN_CANCELLED = "voice.turn.cancelled"
    TURN_FAILED = "voice.turn.failed"
    SESSION_CLOSED = "voice.session.closed"


@dataclass(frozen=True, slots=True)
class VoiceEvent:
    type: VoiceEventType
    voice_session_id: UUID
    session_id: UUID
    data: dict[str, Any]
    voice_turn_id: UUID | None = None
    sequence: int | None = None
    revision: int | None = None
    event_id: UUID = field(default_factory=uuid.uuid4)
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
