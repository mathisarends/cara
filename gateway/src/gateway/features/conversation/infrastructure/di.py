from collections.abc import AsyncIterator

from dishka import Provider, Scope, provide
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from gateway.features.conversation.application import (
    AgentRunner,
    ConversationService,
    EventBroker,
    EventPublisher,
)
from gateway.features.conversation.domain import SessionRepository
from gateway.features.conversation.infrastructure.memory import (
    InMemoryEventBroker,
)
from gateway.features.conversation.infrastructure.persistence import (
    SQLSessionRepository,
)


class ConversationProvider(Provider):
    scope = Scope.APP

    @provide
    def sessions(
        self,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> SessionRepository:
        return SQLSessionRepository(session_factory)

    @provide(scope=Scope.APP)
    def event_broker(self) -> InMemoryEventBroker:
        return InMemoryEventBroker()

    @provide(scope=Scope.APP)
    def broker_port(self, broker: InMemoryEventBroker) -> EventBroker:
        return broker

    @provide(scope=Scope.APP)
    def event_publisher(self, broker: InMemoryEventBroker) -> EventPublisher:
        return broker

    @provide
    async def service(
        self,
        sessions: SessionRepository,
        events: EventPublisher,
        agent: AgentRunner,
    ) -> AsyncIterator[ConversationService]:
        service = ConversationService(sessions, events, agent)
        try:
            yield service
        finally:
            await service.close()
