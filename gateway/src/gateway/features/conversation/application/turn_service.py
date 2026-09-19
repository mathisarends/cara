import logging
from uuid import UUID

from gateway.features.conversation.application.ports import TurnLease
from gateway.features.conversation.application.turn_worker import TurnWorker
from gateway.features.conversation.domain import (
    NoActiveTurnError,
    Session,
    SessionBusyError,
    SessionNotFoundError,
    SessionRepository,
)
from gateway.shared import Transaction

logger = logging.getLogger(__name__)

_MESSAGE_PREVIEW_LENGTH = 200


class TurnService:
    """Handle request-scoped commands and defer long-lived work until commit."""

    def __init__(
        self,
        sessions: SessionRepository,
        lease: TurnLease,
        transaction: Transaction,
        worker: TurnWorker,
    ) -> None:
        self._sessions = sessions
        self._lease = lease
        self._transaction = transaction
        self._worker = worker

    async def prepare(self, session_id: UUID) -> None:
        await self._require_session(session_id)
        await self._worker.prepare(session_id)

    async def finish(self, session_id: UUID) -> None:
        await self._require_session(session_id)
        await self._worker.finish(session_id)

    async def start(self, *, session_id: UUID, text: str) -> UUID:
        session = await self._require_session(session_id)
        if not await self._lease.acquire(session_id):
            raise SessionBusyError(session_id)
        session = await self._require_session(session_id)
        logger.info(
            "User message for session %s on channel %s: %r",
            session_id,
            session.channel.name,
            _preview(text),
        )
        input_message = session.add_user_message(text)
        await self._sessions.save(session)
        self._transaction.after_commit(
            lambda: self._worker.start_committed(
                session_id=session_id,
                text=text,
                input_id=input_message.id,
            )
        )
        return input_message.id

    async def steer(self, *, session_id: UUID, text: str) -> None:
        session = await self._require_session(session_id)
        if not session.turn_active:
            raise NoActiveTurnError(session_id)
        await self._worker.steer(session_id=session_id, text=text)

    async def cancel(self, session_id: UUID) -> None:
        await self._require_session(session_id)
        await self._worker.cancel(session_id)

    async def _require_session(self, session_id: UUID) -> Session:
        session = await self._sessions.find_by_id(session_id)
        if session is None:
            raise SessionNotFoundError(session_id)
        return session


def _preview(text: str) -> str:
    normalized = " ".join(text.split())
    if len(normalized) <= _MESSAGE_PREVIEW_LENGTH:
        return normalized
    return f"{normalized[: _MESSAGE_PREVIEW_LENGTH - 1]}…"
