from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.orm.interfaces import ORMOption

from gateway.features.conversation.domain import (
    AssistantMessage,
    ChannelRef,
    Session,
    SessionRepository,
    SortOrder,
    ToolCall,
    ToolCallSequence,
    ToolCallState,
    UserMessage,
)
from gateway.features.conversation.infrastructure.orm import (
    SessionAssistantMessageModel,
    SessionModel,
    SessionToolCallModel,
    SessionToolCallSequenceModel,
    SessionUserMessageModel,
)
from gateway.platform.database import Repository


class SQLSessionRepository(
    Repository[SessionModel, Session],
    SessionRepository,
):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, SessionModel)

    async def find_latest_by_channel(self, channel: ChannelRef) -> Session | None:
        statement = (
            select(SessionModel)
            .where(SessionModel.channel_name == channel.name)
            .order_by(SessionModel.created_at.desc(), SessionModel.id.desc())
            .limit(1)
            .options(*self._load_options())
        )
        model = await self._session.scalar(statement)
        return self._to_domain(model) if model is not None else None

    async def find_many(self, *, limit: int, order: SortOrder) -> tuple[Session, ...]:
        if order is SortOrder.ASCENDING:
            ordering = (SessionModel.created_at.asc(), SessionModel.id.asc())
        else:
            ordering = (SessionModel.created_at.desc(), SessionModel.id.desc())
        statement = (
            select(SessionModel)
            .order_by(*ordering)
            .limit(limit)
            .options(*self._load_options())
        )
        models = await self._session.scalars(statement)
        return tuple(self._to_domain(model) for model in models)

    def _load_options(self) -> Sequence[ORMOption]:
        return (
            selectinload(SessionModel.user_messages),
            selectinload(SessionModel.assistant_messages),
            selectinload(SessionModel.tool_call_sequences).selectinload(
                SessionToolCallSequenceModel.calls
            ),
        )

    def _to_domain(self, orm: SessionModel) -> Session:
        positioned_entries = [
            *(
                (model.position, _user_message_to_domain(model))
                for model in orm.user_messages
            ),
            *(
                (model.position, _assistant_message_to_domain(model))
                for model in orm.assistant_messages
            ),
            *(
                (model.position, _tool_call_sequence_to_domain(model))
                for model in orm.tool_call_sequences
            ),
        ]
        positioned_entries.sort(key=lambda item: item[0])
        return Session(
            channel=ChannelRef(orm.channel_name),
            id=orm.id,
            created_at=_as_utc(orm.created_at),
            turn_active=orm.turn_active,
            inactivity_timeout=(
                timedelta(seconds=orm.inactivity_timeout_seconds)
                if orm.inactivity_timeout_seconds is not None
                else None
            ),
            entries=[entry for _, entry in positioned_entries],
        )

    def _to_orm(self, domain: Session) -> SessionModel:
        model = SessionModel(
            id=domain.id,
            created_at=domain.created_at,
            channel_name=domain.channel.name,
            inactivity_timeout_seconds=(
                domain.inactivity_timeout.total_seconds()
                if domain.inactivity_timeout is not None
                else None
            ),
            turn_active=domain.turn_active,
        )
        for position, entry in enumerate(domain.entries):
            if isinstance(entry, UserMessage):
                model.user_messages.append(
                    SessionUserMessageModel(
                        id=entry.id,
                        created_at=entry.created_at,
                        session_id=domain.id,
                        position=position,
                        content=entry.content,
                    )
                )
                continue
            if isinstance(entry, AssistantMessage):
                model.assistant_messages.append(
                    SessionAssistantMessageModel(
                        id=entry.id,
                        created_at=entry.created_at,
                        session_id=domain.id,
                        position=position,
                        content=entry.content,
                    )
                )
                continue
            sequence_model = SessionToolCallSequenceModel(
                id=entry.id,
                created_at=entry.created_at,
                session_id=domain.id,
                position=position,
            )
            sequence_model.calls = [
                SessionToolCallModel(
                    id=call.id,
                    created_at=call.created_at,
                    sequence_id=entry.id,
                    position=call_position,
                    call_id=call.call_id,
                    function_name=call.function_name,
                    function_arguments=call.function_arguments,
                    state=call.state.value,
                    result=call.result,
                    error=call.error,
                )
                for call_position, call in enumerate(entry.calls)
            ]
            model.tool_call_sequences.append(sequence_model)
        return model


def _user_message_to_domain(model: SessionUserMessageModel) -> UserMessage:
    return UserMessage(
        model.content,
        id=model.id,
        created_at=_as_utc(model.created_at),
    )


def _assistant_message_to_domain(
    model: SessionAssistantMessageModel,
) -> AssistantMessage:
    return AssistantMessage(
        model.content,
        id=model.id,
        created_at=_as_utc(model.created_at),
    )


def _tool_call_sequence_to_domain(
    model: SessionToolCallSequenceModel,
) -> ToolCallSequence:
    return ToolCallSequence(
        calls=[
            ToolCall(
                call_id=call.call_id,
                function_name=call.function_name,
                function_arguments=call.function_arguments,
                state=ToolCallState(call.state),
                result=call.result,
                error=call.error,
                id=call.id,
                created_at=_as_utc(call.created_at),
            )
            for call in model.calls
        ],
        id=model.id,
        created_at=_as_utc(model.created_at),
    )


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
