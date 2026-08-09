from collections.abc import AsyncIterator

from dishka import Provider, Scope, provide

from gateway.application import (
    AgentRunner,
    EventBroker,
    EventPublisher,
    GatewayService,
    RunRepository,
    SessionRepository,
)
from gateway.infrastructure import (
    InMemoryEventBroker,
    InMemoryRunRepository,
    InMemorySessionRepository,
)


class GatewayProvider(Provider):
    scope = Scope.APP

    def __init__(self, agent: AgentRunner) -> None:
        self._agent = agent
        super().__init__()

    @provide
    def agent(self) -> AgentRunner:
        return self._agent

    @provide
    def sessions(self) -> SessionRepository:
        return InMemorySessionRepository()

    @provide
    def runs(self) -> RunRepository:
        return InMemoryRunRepository()

    @provide
    def event_broker(self) -> InMemoryEventBroker:
        return InMemoryEventBroker()

    @provide
    def broker_port(self, broker: InMemoryEventBroker) -> EventBroker:
        return broker

    @provide
    def event_publisher(self, broker: InMemoryEventBroker) -> EventPublisher:
        return broker

    @provide
    async def service(
        self,
        sessions: SessionRepository,
        runs: RunRepository,
        events: EventPublisher,
        agent: AgentRunner,
    ) -> AsyncIterator[GatewayService]:
        service = GatewayService(sessions, runs, events, agent)
        try:
            yield service
        finally:
            await service.close()
