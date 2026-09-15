from uuid import UUID

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from gateway.features.conversation.application import TurnLease
from gateway.features.conversation.infrastructure.orm import SessionModel


class SQLTurnLease(TurnLease):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def acquire(self, session_id: UUID) -> bool:
        statement = (
            update(SessionModel)
            .where(SessionModel.id == session_id, SessionModel.turn_active.is_(False))
            .values(turn_active=True)
        )
        result = await self._session.execute(statement)
        return result.rowcount == 1

    async def release(self, session_id: UUID) -> None:
        statement = (
            update(SessionModel)
            .where(SessionModel.id == session_id)
            .values(turn_active=False)
        )
        await self._session.execute(statement)
