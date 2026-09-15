from collections.abc import AsyncIterator

from dishka import Provider, Scope, provide
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from gateway.features.conversation.application import (
    AgentRuntime,
    EventPublisher,
    SessionService,
    TurnLease,
    TurnService,
)
from gateway.features.conversation.domain import SessionRepository
from gateway.features.conversation.infrastructure.repository import (
    SQLSessionRepository,
)
from gateway.features.conversation.infrastructure.turn_lease import SQLTurnLease


class ConversationProvider(Provider):
    scope = Scope.APP

    @provide
    def sessions(
        self,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> SessionRepository:
        return SQLSessionRepository(session_factory)

    @provide
    def session_service(self, sessions: SessionRepository) -> SessionService:
        return SessionService(sessions)

    @provide
    def turn_lease(
        self,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> TurnLease:
        return SQLTurnLease(session_factory)

    @provide
    async def turn_service(
        self,
        sessions: SessionRepository,
        session_service: SessionService,
        lease: TurnLease,
        events: EventPublisher,
        agent: AgentRuntime,
    ) -> AsyncIterator[TurnService]:
        service = TurnService(sessions, session_service, lease, events, agent)
        try:
            yield service
        finally:
            await service.close()
