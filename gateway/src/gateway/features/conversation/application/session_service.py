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

    async def create(
        self,
        *,
        channel: ChannelRef,
    ) -> Session:
        return await _create(self._sessions, channel)

    async def open(
        self,
        *,
        channel: ChannelRef,
    ) -> Session:
        session = await self._sessions.find_latest_by_channel(channel)
        if session is None:
            return await _create(self._sessions, channel)
        logger.info(
            "Opened existing conversation session %s for channel %s",
            session.id,
            channel.name,
        )
        return session

    async def list(self, *, limit: int, order: SortOrder) -> tuple[Session, ...]:
        return await self._sessions.find_many(limit=limit, order=order)

    async def get(self, session_id: UUID) -> Session:
        session = await self._sessions.find_by_id(session_id)
        if session is None:
            raise SessionNotFoundError(session_id)
        return session


async def _create(sessions: SessionRepository, channel: ChannelRef) -> Session:
    current = await sessions.find_latest_by_channel(channel)
    if current is not None:
        current.supersede()
        await sessions.save(current)
    session = Session.create(channel)
    saved = await sessions.save(session)
    logger.info(
        "Created conversation session %s for channel %s",
        saved.id,
        channel.name,
    )
    return saved
