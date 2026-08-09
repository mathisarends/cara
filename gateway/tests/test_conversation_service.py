import asyncio
from uuid import UUID

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel import SQLModel

from gateway.features.conversation.application import AgentEventBus, AgentRunner
from gateway.features.conversation.application.ports import EventPublisher
from gateway.features.conversation.application.service import ConversationService
from gateway.features.conversation.domain import GatewayEvent, GatewayEventType
from gateway.features.conversation.infrastructure.persistence import (
    SQLSessionRepository,
)


class _FailingAgentRunner(AgentRunner):
    async def run(
        self,
        session_id: UUID,
        metadata: dict[str, object],
        event_bus: AgentEventBus,
    ) -> None:
        del session_id, metadata, event_bus
        raise NotImplementedError


class _RecordingPublisher(EventPublisher):
    def __init__(self) -> None:
        self.events: list[GatewayEvent] = []

    async def publish(self, event: GatewayEvent) -> None:
        self.events.append(event)


def test_failed_turn_publishes_turn_failed_event() -> None:
    asyncio.run(_assert_failed_turn_is_published())


async def _assert_failed_turn_is_published() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(SQLModel.metadata.create_all)
    repository = SQLSessionRepository(
        async_sessionmaker(engine, expire_on_commit=False)
    )
    publisher = _RecordingPublisher()
    service = ConversationService(repository, publisher, _FailingAgentRunner())
    session = await service.create_session({})

    await service.start_turn(session.id, "hello", {})
    await _wait_for_event(publisher)
    await service.close()

    assert [event.type for event in publisher.events] == [GatewayEventType.TURN_FAILED]
    failure = publisher.events[0]
    assert failure.session_id == session.id
    # NotImplementedError carries no message, so the type name stands in for it.
    assert failure.data == {
        "code": "NotImplementedError",
        "message": "NotImplementedError",
    }

    await engine.dispose()


async def _wait_for_event(
    publisher: _RecordingPublisher,
    timeout: float = 5.0,
) -> None:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while not publisher.events and loop.time() < deadline:
        await asyncio.sleep(0.01)
