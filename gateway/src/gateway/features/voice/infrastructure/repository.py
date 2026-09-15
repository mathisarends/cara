from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from gateway.features.voice.domain import (
    Activation,
    AudioEncoding,
    AudioFormat,
    VoiceSession,
    VoiceSessionRepository,
    VoiceSessionStatus,
    VoiceTurn,
    VoiceTurnStatus,
)
from gateway.features.voice.infrastructure.orm import VoiceSessionModel, VoiceTurnModel
from gateway.platform.database import Repository


class SQLVoiceSessionRepository(
    Repository[VoiceSessionModel, VoiceSession],
    VoiceSessionRepository,
):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, VoiceSessionModel)

    async def find_by_device(
        self,
        device_id: str,
        status: VoiceSessionStatus | None = None,
    ) -> tuple[VoiceSession, ...]:
        return await self.find_many(device_id=device_id, status=status)

    async def find_many(
        self,
        *,
        session_id: UUID | None = None,
        device_id: str | None = None,
        status: VoiceSessionStatus | None = None,
    ) -> tuple[VoiceSession, ...]:
        statement = select(VoiceSessionModel)
        if session_id is not None:
            statement = statement.where(VoiceSessionModel.session_id == session_id)
        if device_id is not None:
            statement = statement.where(VoiceSessionModel.device_id == device_id)
        if status is not None:
            statement = statement.where(VoiceSessionModel.status == status)
        statement = statement.order_by(
            VoiceSessionModel.created_at,
            VoiceSessionModel.id,
        )
        models = await self._session.scalars(statement.options(*self._load_options()))
        return tuple(self._to_domain(model) for model in models)

    def _to_domain(self, orm: VoiceSessionModel) -> VoiceSession:
        input_format = AudioFormat(
            AudioEncoding(orm.input_encoding),
            orm.input_sample_rate,
            orm.input_channels,
        )
        output_format = AudioFormat(
            AudioEncoding(orm.output_encoding),
            orm.output_sample_rate,
            orm.output_channels,
        )
        return VoiceSession(
            orm.session_id,
            orm.device_id,
            input_format,
            output_format,
            turns=tuple(_turn_to_domain(turn) for turn in orm.turns),
            status=VoiceSessionStatus(orm.status),
            id=orm.id,
            created_at=_as_utc(orm.created_at),
            last_sequence=orm.last_sequence,
            closed_at=_optional_utc(orm.closed_at),
            close_reason=orm.close_reason,
        )

    def _to_orm(self, domain: VoiceSession) -> VoiceSessionModel:
        return VoiceSessionModel(
            id=domain.id,
            created_at=domain.created_at,
            session_id=domain.session_id,
            device_id=domain.device_id,
            status=domain.status,
            input_encoding=domain.input_format.encoding,
            input_sample_rate=domain.input_format.sample_rate,
            input_channels=domain.input_format.channels,
            output_encoding=domain.output_format.encoding,
            output_sample_rate=domain.output_format.sample_rate,
            output_channels=domain.output_format.channels,
            last_sequence=domain.last_sequence,
            closed_at=domain.closed_at,
            close_reason=domain.close_reason,
            turns=[_turn_to_orm(domain.id, turn) for turn in domain.turns],
        )

    def _load_options(self):
        return (selectinload(VoiceSessionModel.turns),)


def _turn_to_domain(orm: VoiceTurnModel) -> VoiceTurn:
    return VoiceTurn(
        orm.index,
        Activation(orm.activation),
        VoiceTurnStatus(orm.status),
        id=orm.id,
        created_at=_as_utc(orm.created_at),
        transcript=orm.transcript,
        user_message_id=orm.user_message_id,
        stt_provider=orm.stt_provider,
        tts_provider=orm.tts_provider,
        error_code=orm.error_code,
        error_message=orm.error_message,
        input_ended_at=_optional_utc(orm.input_ended_at),
        transcribed_at=_optional_utc(orm.transcribed_at),
        speech_started_at=_optional_utc(orm.speech_started_at),
        ended_at=_optional_utc(orm.ended_at),
    )


def _turn_to_orm(voice_session_id: UUID, domain: VoiceTurn) -> VoiceTurnModel:
    return VoiceTurnModel(
        id=domain.id,
        created_at=domain.created_at,
        voice_session_id=voice_session_id,
        index=domain.index,
        activation=domain.activation,
        status=domain.status,
        transcript=domain.transcript,
        user_message_id=domain.user_message_id,
        stt_provider=domain.stt_provider,
        tts_provider=domain.tts_provider,
        error_code=domain.error_code,
        error_message=domain.error_message,
        input_ended_at=domain.input_ended_at,
        transcribed_at=domain.transcribed_at,
        speech_started_at=domain.speech_started_at,
        ended_at=domain.ended_at,
    )


def _optional_utc(value: datetime | None) -> datetime | None:
    return None if value is None else _as_utc(value)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
