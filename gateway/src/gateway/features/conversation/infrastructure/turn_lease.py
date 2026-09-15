from uuid import UUID

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from gateway.features.conversation.application import TurnLease
from gateway.platform.database import SessionModel


class SQLTurnLease(TurnLease):
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        self._session_factory = session_factory

    async def acquire(self, session_id: UUID) -> bool:
        statement = (
            update(SessionModel)
            .where(SessionModel.id == session_id, SessionModel.turn_active.is_(False))
            .values(turn_active=True)
        )
        async with self._session_factory() as database:
            result = await database.execute(statement)
            await database.commit()
            return result.rowcount == 1

    async def release(self, session_id: UUID) -> None:
        statement = (
            update(SessionModel)
            .where(SessionModel.id == session_id)
            .values(turn_active=False)
        )
        async with self._session_factory() as database:
            await database.execute(statement)
            await database.commit()
