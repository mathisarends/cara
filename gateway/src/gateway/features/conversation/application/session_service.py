import asyncio
import logging
from uuid import UUID

from gateway.features.conversation.domain import (
    ChannelRef,
    Session,
    SessionNotFoundError,
    SessionRepository,
    SortOrder,
)

logger = logging.getLogger(__name__)


class SessionService:
    def __init__(self, sessions: SessionRepository) -> None:
        self._sessions = sessions
        self._open_lock = asyncio.Lock()

    async def create(
        self,
        *,
        channel: ChannelRef,
    ) -> Session:
        session = Session.create(channel)
        saved = await self._sessions.save(session)
        logger.info(
            "Created conversation session %s for channel %s",
            saved.id,
            channel.name,
        )
        return saved

    async def open(
        self,
        *,
        channel: ChannelRef,
    ) -> Session:
        async with self._open_lock:
            session = await self._sessions.find_latest_by_channel(channel)
            if session is not None:
                logger.info(
                    "Opened existing conversation session %s for channel %s",
                    session.id,
                    channel.name,
                )
                return session
            return await self.create(channel=channel)

    async def list(self, *, limit: int, order: SortOrder) -> tuple[Session, ...]:
        return await self._sessions.find_many(limit=limit, order=order)

    async def get(self, session_id: UUID) -> Session:
        session = await self._sessions.find_by_id(session_id)
        if session is None:
            raise SessionNotFoundError(session_id)
        return session
