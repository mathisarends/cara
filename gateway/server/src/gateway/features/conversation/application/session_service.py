import asyncio
from typing import Any
from uuid import UUID

from gateway.features.conversation.domain import (
    ChannelRef,
    Session,
    SessionNotFoundError,
    SessionRepository,
)


class SessionService:
    def __init__(self, sessions: SessionRepository) -> None:
        self._sessions = sessions
        self._open_lock = asyncio.Lock()

    async def create(
        self,
        *,
        channel: ChannelRef,
        metadata: dict[str, Any],
    ) -> Session:
        session = Session.create(channel, metadata)
        return await self._sessions.save(session)

    async def open(
        self,
        *,
        channel: ChannelRef,
        metadata: dict[str, Any],
    ) -> Session:
        async with self._open_lock:
            session = await self._sessions.find_latest_by_channel(channel)
            if session is not None:
                return session
            return await self.create(channel=channel, metadata=metadata)

    async def get(self, session_id: UUID) -> Session:
        session = await self._sessions.find_by_id(session_id)
        if session is None:
            raise SessionNotFoundError(session_id)
        return session
