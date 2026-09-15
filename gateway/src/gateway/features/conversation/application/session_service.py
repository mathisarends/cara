import asyncio
import logging
from datetime import UTC, datetime, timedelta
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
        inactivity_timeout: timedelta | None = None,
    ) -> Session:
        async with self._sessions() as sessions:
            return await _create(
                sessions,
                channel,
                inactivity_timeout=inactivity_timeout,
            )

    async def open(
        self,
        *,
        channel: ChannelRef,
        inactivity_timeout: timedelta | None = None,
    ) -> Session:
        # The lock also spans the commit, so concurrent opens never both create.
        async with self._open_lock, self._sessions() as sessions:
            session = await sessions.find_latest_by_channel(channel)
            if session is None:
                return await _create(
                    sessions,
                    channel,
                    inactivity_timeout=inactivity_timeout,
                )
            if inactivity_timeout is not None:
                session.set_inactivity_timeout(inactivity_timeout)
            if session.is_inactive_at(datetime.now(UTC)):
                return await _create(
                    sessions,
                    channel,
                    inactivity_timeout=session.inactivity_timeout,
                )
            if inactivity_timeout is not None:
                session = await sessions.save(session)
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


async def _create(
    sessions: SessionRepository,
    channel: ChannelRef,
    *,
    inactivity_timeout: timedelta | None = None,
) -> Session:
    session = Session.create(channel)
    session.set_inactivity_timeout(inactivity_timeout)
    saved = await sessions.save(session)
    logger.info(
        "Created conversation session %s for channel %s",
        saved.id,
        channel.name,
    )
    return saved
