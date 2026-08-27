import asyncio
from collections.abc import AsyncIterator

from agent_plugin_api import (
    AgentEvent,
    AgentRunner,
    AgentRunRequest,
    AgentSessionRef,
)
from gateway.features.conversation.application.service import ConversationService
from gateway.features.conversation.domain import GatewayEvent, GatewayEventType
from gateway.features.conversation.infrastructure.memory import InMemoryEventBroker
from gateway.features.conversation.infrastructure.persistence import (
    SQLSessionRepository,
)
from gateway.features.conversation.presentation.rpc import (
    CreateSessionParams,
    SessionParams,
    StartTurnParams,
)
from gateway.features.conversation.presentation.schemas import SessionChannel
from gateway.features.conversation.presentation.session_rpc_methods import (
    SessionRpcMethods,
)
from gateway.features.conversation.presentation.subscription_rpc_methods import (
    SubscriptionRpcMethods,
)
from gateway.features.conversation.presentation.turn_rpc_methods import (
    TurnRpcMethods,
)

_CHANNEL = SessionChannel(name="voice", account_id="local")


class _NullAgentRunner(AgentRunner):
    def __init__(self) -> None:
        self.lifecycle: list[tuple[str, AgentSessionRef]] = []

    async def prepare(self, session: AgentSessionRef) -> None:
        self.lifecycle.append(("prepare", session))

    async def run(
        self,
        request: AgentRunRequest,
    ) -> AsyncIterator[AgentEvent]:
        del request
        return
        yield

    async def finish(self, session: AgentSessionRef) -> None:
        self.lifecycle.append(("finish", session))

    async def close(self) -> None:
        pass


class _HangingAgentRunner(AgentRunner):
    async def run(
        self,
        request: AgentRunRequest,
    ) -> AsyncIterator[AgentEvent]:
        del request
        await asyncio.Event().wait()
        yield

    async def close(self) -> None:
        pass


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


async def test_start_turn_runs_the_agent_and_returns_the_session_id(
    session_repository: SQLSessionRepository,
) -> None:
    broker = InMemoryEventBroker()
    service = ConversationService(session_repository, broker, _NullAgentRunner())
    session_methods = SessionRpcMethods(service)
    subscription_methods = SubscriptionRpcMethods(service, broker, "client-1")
    turn_methods = TurnRpcMethods(service)
    receiver = broker.connect("client-1")
    created = await session_methods.create_session(
        CreateSessionParams(channel=_CHANNEL)
    )
    await subscription_methods.subscribe_session(SessionParams(session_id=created.id))

    result = await turn_methods.start_turn(
        StartTurnParams(session_id=created.id, message="hello")
    )

    assert result.session_id == created.id
    await _wait_for_event(receiver, GatewayEventType.TURN_COMPLETED)
    await service.close()


async def test_prepare_and_finish_turn_forward_the_session(
    session_repository: SQLSessionRepository,
) -> None:
    broker = InMemoryEventBroker()
    runner = _NullAgentRunner()
    service = ConversationService(session_repository, broker, runner)
    session_methods = SessionRpcMethods(service)
    turn_methods = TurnRpcMethods(service)
    created = await session_methods.create_session(
        CreateSessionParams(channel=_CHANNEL)
    )

    prepared = await turn_methods.prepare_turn(SessionParams(session_id=created.id))
    finished = await turn_methods.finish_turn(SessionParams(session_id=created.id))

    assert prepared.session_id == created.id
    assert finished.session_id == created.id
    assert [event for event, _ in runner.lifecycle] == ["prepare", "finish"]
    assert all(session.id == created.id for _, session in runner.lifecycle)


async def test_cancel_turn_stops_an_active_turn(
    session_repository: SQLSessionRepository,
) -> None:
    broker = InMemoryEventBroker()
    service = ConversationService(session_repository, broker, _HangingAgentRunner())
    session_methods = SessionRpcMethods(service)
    subscription_methods = SubscriptionRpcMethods(service, broker, "client-1")
    turn_methods = TurnRpcMethods(service)
    receiver = broker.connect("client-1")
    created = await session_methods.create_session(
        CreateSessionParams(channel=_CHANNEL)
    )
    await subscription_methods.subscribe_session(SessionParams(session_id=created.id))
    await turn_methods.start_turn(
        StartTurnParams(session_id=created.id, message="hello")
    )

    result = await turn_methods.cancel_turn(SessionParams(session_id=created.id))

    assert result.session_id == created.id
    await _wait_for_event(receiver, GatewayEventType.TURN_CANCELLED)
    await service.close()
