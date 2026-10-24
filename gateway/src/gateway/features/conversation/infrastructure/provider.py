from collections.abc import AsyncIterator

from dishka import AsyncContainer, Provider, Scope, provide
from sqlalchemy.ext.asyncio import AsyncSession

from gateway.features.conversation.application import (
    AgentRuntime,
    EventPublisher,
    SessionService,
    TurnLease,
    TurnService,
    TurnWorker,
)
from gateway.features.conversation.domain import SessionRepository
from gateway.features.conversation.infrastructure.repository import (
    SQLSessionRepository,
)
from gateway.features.conversation.infrastructure.turn_lease import SQLTurnLease
from gateway.platform.database import ScopedUnitOfWork
from gateway.shared import Transaction, UnitOfWork


class ConversationProvider(Provider):
    @provide(scope=Scope.REQUEST)
    def sessions(self, session: AsyncSession) -> SessionRepository:
        return SQLSessionRepository(session)

    @provide(scope=Scope.APP)
    def sessions_unit_of_work(
        self,
        container: AsyncContainer,
    ) -> UnitOfWork[SessionRepository]:
        return ScopedUnitOfWork(container, SessionRepository)

    @provide(scope=Scope.REQUEST)
    def session_service(
        self,
        session_repository: SessionRepository,
    ) -> SessionService:
        return SessionService(session_repository)

    @provide(scope=Scope.APP)
    def session_service_unit_of_work(
        self,
        container: AsyncContainer,
    ) -> UnitOfWork[SessionService]:
        return ScopedUnitOfWork(container, SessionService)

    @provide(scope=Scope.REQUEST)
    def turn_lease(self, session: AsyncSession) -> TurnLease:
        return SQLTurnLease(session)

    @provide(scope=Scope.APP)
    def turn_lease_unit_of_work(
        self,
        container: AsyncContainer,
    ) -> UnitOfWork[TurnLease]:
        return ScopedUnitOfWork(container, TurnLease)

    @provide(scope=Scope.APP)
    async def turn_worker(
        self,
        sessions: UnitOfWork[SessionRepository],
        leases: UnitOfWork[TurnLease],
        events: EventPublisher,
        agent: AgentRuntime,
    ) -> AsyncIterator[TurnWorker]:
        worker = TurnWorker(sessions, leases, events, agent)
        try:
            yield worker
        finally:
            await worker.close()

    @provide(scope=Scope.REQUEST)
    def turn_service(
        self,
        sessions: SessionRepository,
        lease: TurnLease,
        transaction: Transaction,
        worker: TurnWorker,
    ) -> TurnService:
        return TurnService(sessions, lease, transaction, worker)
