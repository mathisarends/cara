import asyncio
from collections.abc import AsyncIterator
from uuid import uuid4

import pytest

from agent_plugin_api import AgentEvent, AgentRunner, AgentRunRequest
from gateway.features.conversation.application.service import ConversationService
from gateway.features.conversation.domain import SessionNotFoundError
from gateway.features.conversation.infrastructure.memory import InMemoryEventBroker
from gateway.features.conversation.infrastructure.persistence import (
    SQLSessionRepository,
)
from gateway.features.conversation.presentation.rpc import (
    CreateSessionParams,
    OpenSessionParams,
    SessionParams,
)
from gateway.features.conversation.presentation.schemas import (
    SessionChannel,
    SessionSnapshotResponse,
)
from gateway.features.conversation.presentation.session_rpc_methods import (
    SessionRpcMethods,
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
def service(
    session_repository: SQLSessionRepository,
) -> ConversationService:
    return ConversationService(
        session_repository, InMemoryEventBroker(), _NullAgentRunner()
    )


@pytest.fixture
def methods(service: ConversationService) -> SessionRpcMethods:
    return SessionRpcMethods(service)


async def test_create_session_persists_metadata(
    methods: SessionRpcMethods,
    session_repository: SQLSessionRepository,
) -> None:
    response = await methods.create_session(
        CreateSessionParams(channel=_CHANNEL, metadata={"c": "t"})
    )

    assert response.channel == _CHANNEL
    assert response.metadata == {"c": "t"}
    assert await session_repository.find_by_id(response.id) is not None


async def test_create_session_always_creates_a_fresh_session(
    methods: SessionRpcMethods,
) -> None:
    first = await methods.create_session(CreateSessionParams(channel=_CHANNEL))
    second = await methods.create_session(CreateSessionParams(channel=_CHANNEL))

    assert second.id != first.id


async def test_open_session_reuses_the_latest_session_for_the_channel(
    methods: SessionRpcMethods,
) -> None:
    created = await methods.create_session(CreateSessionParams(channel=_CHANNEL))

    opened = await methods.open_session(OpenSessionParams(channel=_CHANNEL))

    assert opened.id == created.id


async def test_concurrent_open_session_calls_resolve_to_one_session(
    methods: SessionRpcMethods,
) -> None:
    first, second = await asyncio.gather(
        methods.open_session(OpenSessionParams(channel=_CHANNEL)),
        methods.open_session(OpenSessionParams(channel=_CHANNEL)),
    )

    assert second.id == first.id


async def test_open_session_does_not_cross_channel_boundaries(
    methods: SessionRpcMethods,
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


async def test_get_session_returns_a_snapshot(methods: SessionRpcMethods) -> None:
    created = await methods.create_session(CreateSessionParams(channel=_CHANNEL))

    snapshot = await methods.get_session(SessionParams(session_id=created.id))

    assert isinstance(snapshot, SessionSnapshotResponse)
    assert snapshot.session.id == created.id


async def test_get_session_raises_for_an_unknown_session(
    methods: SessionRpcMethods,
) -> None:
    with pytest.raises(SessionNotFoundError):
        await methods.get_session(SessionParams(session_id=uuid4()))
