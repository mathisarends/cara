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
from gateway.shared import UnitOfWork

logger = logging.getLogger(__name__)


class SessionService:
    def __init__(self, sessions: UnitOfWork[SessionRepository]) -> None:
        self._sessions = sessions
        self._open_lock = asyncio.Lock()

    async def create(
        self,
        *,
        channel: ChannelRef,
    ) -> Session:
        async with self._sessions() as sessions:
            return await _create(sessions, channel)

    async def open(
        self,
        *,
        channel: ChannelRef,
    ) -> Session:
        # The lock also spans the commit, so concurrent opens never both create.
        async with self._open_lock, self._sessions() as sessions:
            session = await sessions.find_latest_by_channel(channel)
            if session is None:
                return await _create(sessions, channel)
            logger.info(
                "Opened existing conversation session %s for channel %s",
                session.id,
                channel.name,
            )
            return session

    async def list(self, *, limit: int, order: SortOrder) -> tuple[Session, ...]:
        async with self._sessions() as sessions:
            return await sessions.find_many(limit=limit, order=order)

    async def get(self, session_id: UUID) -> Session:
        async with self._sessions() as sessions:
            session = await sessions.find_by_id(session_id)
        if session is None:
            raise SessionNotFoundError(session_id)
        return session


async def _create(sessions: SessionRepository, channel: ChannelRef) -> Session:
    saved = await sessions.save(Session.create(channel))
    logger.info(
        "Created conversation session %s for channel %s",
        saved.id,
        channel.name,
    )
    return saved
