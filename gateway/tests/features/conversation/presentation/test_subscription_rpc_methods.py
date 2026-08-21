import asyncio
from collections.abc import AsyncIterator
from uuid import uuid4

import pytest

from agent_plugin_api import AgentEvent, AgentRunner, AgentRunRequest
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
    SessionParams,
)
from gateway.features.conversation.presentation.schemas import SessionChannel
from gateway.features.conversation.presentation.session_rpc_methods import (
    SessionRpcMethods,
)
from gateway.features.conversation.presentation.subscription_rpc_methods import (
    SubscriptionRpcMethods,
)

_CHANNEL = SessionChannel(name="voice", account_id="local")


class _NullAgentRunner(AgentRunner):
    async def run(
        self,
        request: AgentRunRequest,
    ) -> AsyncIterator[AgentEvent]:
        del request
        return
        yield

    async def close(self) -> None:
        pass


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
def session_methods(service: ConversationService) -> SessionRpcMethods:
    return SessionRpcMethods(service)


@pytest.fixture
def methods(
    service: ConversationService,
    broker: InMemoryEventBroker,
) -> SubscriptionRpcMethods:
    return SubscriptionRpcMethods(service, broker, "client-1")


async def test_subscribe_session_registers_the_connection_with_the_broker(
    session_methods: SessionRpcMethods,
    methods: SubscriptionRpcMethods,
    broker: InMemoryEventBroker,
) -> None:
    created = await session_methods.create_session(
        CreateSessionParams(channel=_CHANNEL)
    )
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
    methods: SubscriptionRpcMethods,
) -> None:
    with pytest.raises(SessionNotFoundError):
        await methods.subscribe_session(SessionParams(session_id=uuid4()))


async def test_unsubscribe_session_removes_the_connection_from_the_broker(
    session_methods: SessionRpcMethods,
    methods: SubscriptionRpcMethods,
    broker: InMemoryEventBroker,
) -> None:
    created = await session_methods.create_session(
        CreateSessionParams(channel=_CHANNEL)
    )
    receiver = broker.connect("client-1")
    await methods.subscribe_session(SessionParams(session_id=created.id))

    result = await methods.unsubscribe_session(SessionParams(session_id=created.id))

    assert result.unsubscribed == created.id
    event = GatewayEvent(
        type=GatewayEventType.CHAT_DELTA,
        session_id=created.id,
        data={"text": "hi"},
    )
    await broker.publish(event)
    with pytest.raises(TimeoutError):
        async with asyncio.timeout(0.05):
            await receiver.receive()
