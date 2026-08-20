import asyncio
from collections.abc import AsyncIterator
from uuid import UUID, uuid4

import pytest

from gateway.features.conversation.application import AgentEvent, AgentRunner
from gateway.features.conversation.application.service import ConversationService
from gateway.features.conversation.domain import (
    GatewayEvent,
    GatewayEventType,
    SessionNotFoundError,
)
from gateway.features.conversation.infrastructure.memory import InMemoryEventBroker
from gateway.features.conversation.infrastructure.persistence import (
    SQLSessionRepository,
)
from gateway.features.conversation.presentation.rpc import (
    CreateSessionParams,
    OpenSessionParams,
    SessionParams,
    StartTurnParams,
)
from gateway.features.conversation.presentation.rpc_methods import (
    ConversationRpcMethods,
)
from gateway.features.conversation.presentation.schemas import (
    SessionChannel,
    SessionSnapshotResponse,
)

_CHANNEL = SessionChannel(name="voice", account_id="local")


class _NullAgentRunner(AgentRunner):
    async def run(
        self,
        session_id: UUID,
        metadata: dict[str, object],
    ) -> AsyncIterator[AgentEvent]:
        del session_id, metadata
        return
        yield


class _HangingAgentRunner(AgentRunner):
    async def run(
        self,
        session_id: UUID,
        metadata: dict[str, object],
    ) -> AsyncIterator[AgentEvent]:
        del session_id, metadata
        await asyncio.Event().wait()
        yield


@pytest.fixture
def broker() -> InMemoryEventBroker:
    return InMemoryEventBroker()


@pytest.fixture
def service(
    session_repository: SQLSessionRepository,
    broker: InMemoryEventBroker,
) -> ConversationService:
    return ConversationService(session_repository, broker, _NullAgentRunner())


@pytest.fixture
def methods(
    service: ConversationService,
    broker: InMemoryEventBroker,
) -> ConversationRpcMethods:
    return ConversationRpcMethods(service, broker, "client-1")


async def _wait_for_event(
    receiver,
    event_type: GatewayEventType,
    timeout: float = 5.0,
) -> GatewayEvent:
    async with asyncio.timeout(timeout):
        while True:
            event = await receiver.receive()
            if event.type is event_type:
                return event


async def test_create_session_persists_metadata(
    methods: ConversationRpcMethods,
    session_repository: SQLSessionRepository,
) -> None:
    response = await methods.create_session(
        CreateSessionParams(channel=_CHANNEL, metadata={"c": "t"})
    )

    assert response.channel == _CHANNEL
    assert response.metadata == {"c": "t"}
    assert await session_repository.find_by_id(response.id) is not None


async def test_create_session_always_creates_a_fresh_session(
    methods: ConversationRpcMethods,
) -> None:
    first = await methods.create_session(CreateSessionParams(channel=_CHANNEL))
    second = await methods.create_session(CreateSessionParams(channel=_CHANNEL))

    assert second.id != first.id


async def test_open_session_reuses_the_latest_session_for_the_channel(
    methods: ConversationRpcMethods,
) -> None:
    created = await methods.create_session(CreateSessionParams(channel=_CHANNEL))

    opened = await methods.open_session(OpenSessionParams(channel=_CHANNEL))

    assert opened.id == created.id


async def test_concurrent_open_session_calls_resolve_to_one_session(
    methods: ConversationRpcMethods,
) -> None:
    first, second = await asyncio.gather(
        methods.open_session(OpenSessionParams(channel=_CHANNEL)),
        methods.open_session(OpenSessionParams(channel=_CHANNEL)),
    )

    assert second.id == first.id


async def test_open_session_does_not_cross_channel_boundaries(
    methods: ConversationRpcMethods,
) -> None:
    first = await methods.open_session(OpenSessionParams(channel=_CHANNEL))

    second = await methods.open_session(
        OpenSessionParams(
            channel=SessionChannel(
                name="voice",
                account_id="someone-else",
            )
        )
    )

    assert second.id != first.id


async def test_get_session_returns_a_snapshot(methods: ConversationRpcMethods) -> None:
    created = await methods.create_session(CreateSessionParams(channel=_CHANNEL))

    snapshot = await methods.get_session(SessionParams(session_id=created.id))

    assert isinstance(snapshot, SessionSnapshotResponse)
    assert snapshot.session.id == created.id


async def test_get_session_raises_for_an_unknown_session(
    methods: ConversationRpcMethods,
) -> None:
    with pytest.raises(SessionNotFoundError):
        await methods.get_session(SessionParams(session_id=uuid4()))


async def test_subscribe_session_registers_the_connection_with_the_broker(
    methods: ConversationRpcMethods,
    broker: InMemoryEventBroker,
) -> None:
    created = await methods.create_session(CreateSessionParams(channel=_CHANNEL))
    receiver = broker.connect("client-1")

    result = await methods.subscribe_session(SessionParams(session_id=created.id))

    assert result.subscribed == created.id
    event = GatewayEvent(
        type=GatewayEventType.CHAT_DELTA,
        session_id=created.id,
        data={"text": "hi"},
    )
    await broker.publish(event)
    assert await receiver.receive() is event


async def test_subscribe_session_raises_for_an_unknown_session(
    methods: ConversationRpcMethods,
) -> None:
    with pytest.raises(SessionNotFoundError):
        await methods.subscribe_session(SessionParams(session_id=uuid4()))


async def test_start_turn_runs_the_agent_and_returns_the_session_id(
    methods: ConversationRpcMethods,
    service: ConversationService,
    broker: InMemoryEventBroker,
) -> None:
    receiver = broker.connect("client-1")
    created = await methods.create_session(CreateSessionParams(channel=_CHANNEL))
    await methods.subscribe_session(SessionParams(session_id=created.id))

    result = await methods.start_turn(
        StartTurnParams(session_id=created.id, message="hello")
    )

    assert result.session_id == created.id
    await _wait_for_event(receiver, GatewayEventType.TURN_COMPLETED)
    await service.close()


async def test_cancel_turn_stops_an_active_turn(
    broker: InMemoryEventBroker,
    session_repository: SQLSessionRepository,
) -> None:
    service = ConversationService(session_repository, broker, _HangingAgentRunner())
    methods = ConversationRpcMethods(service, broker, "client-1")
    receiver = broker.connect("client-1")
    created = await methods.create_session(CreateSessionParams(channel=_CHANNEL))
    await methods.subscribe_session(SessionParams(session_id=created.id))
    await methods.start_turn(StartTurnParams(session_id=created.id, message="hello"))

    result = await methods.cancel_turn(SessionParams(session_id=created.id))

    assert result.session_id == created.id
    await _wait_for_event(receiver, GatewayEventType.TURN_CANCELLED)
    await service.close()
