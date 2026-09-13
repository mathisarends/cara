from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload

from gateway.features.conversation.domain import (
    AssistantMessage,
    ChannelRef,
    Session,
    SessionRepository,
    ToolCall,
    ToolCallSequence,
    ToolCallState,
    UserMessage,
)
from gateway.infrastructure.database import (
    Repository,
    SessionAssistantMessageModel,
    SessionModel,
    SessionToolCallModel,
    SessionToolCallSequenceModel,
    SessionUserMessageModel,
)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


class SQLSessionRepository(
    Repository[SessionModel, Session],
    SessionRepository,
):
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        super().__init__(session_factory, SessionModel)

    async def find_by_id(self, id: UUID) -> Session | None:
        statement = self._with_entries(
            select(SessionModel).where(SessionModel.id == id)
        )
        async with self._session_factory() as database:
            result = await database.execute(statement)
            model = result.scalar_one_or_none()
            return self._to_domain(model) if model is not None else None

    async def find_latest_by_channel(self, channel: ChannelRef) -> Session | None:
        statement = self._with_entries(
            select(SessionModel)
            .where(
                SessionModel.channel_name == channel.name,
                SessionModel.channel_account_id == channel.account_id,
            )
            .order_by(SessionModel.created_at.desc(), SessionModel.id.desc())
            .limit(1)
        )
        async with self._session_factory() as database:
            result = await database.execute(statement)
            model = result.scalar_one_or_none()
            return self._to_domain(model) if model is not None else None

    async def save(self, domain: Session) -> Session:
        async with self._session_factory() as database:
            await database.merge(self._to_orm(domain))
            await database.commit()
        restored = await self.find_by_id(domain.id)
        if restored is None:
            raise RuntimeError(f"Saved session {domain.id} could not be reloaded")
        return restored

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
            channel=ChannelRef(
                name=orm.channel_name,
                account_id=orm.channel_account_id,
            ),
            id=orm.id,
            created_at=_as_utc(orm.created_at),
            metadata=dict(orm.metadata_json),
            turn_active=orm.turn_active,
            entries=[entry for _, entry in positioned_entries],
        )

    def _to_orm(self, domain: Session) -> SessionModel:
        model = SessionModel(
            id=domain.id,
            created_at=domain.created_at,
            channel_name=domain.channel.name,
            channel_account_id=domain.channel.account_id,
            metadata_json=dict(domain.metadata),
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

    def _with_entries(self, statement: Select[tuple[SessionModel]]):
        return statement.options(
            selectinload(SessionModel.user_messages),
            selectinload(SessionModel.assistant_messages),
            selectinload(SessionModel.tool_call_sequences).selectinload(
                SessionToolCallSequenceModel.calls
            ),
        )


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
