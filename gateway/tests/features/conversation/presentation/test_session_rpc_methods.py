import asyncio
from collections.abc import AsyncIterator
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from agent_plugin_api import AgentEvent, AgentRunner, AgentRunRequest
from gateway.features.conversation.application import (
    ConversationEvent,
    EventPublisher,
    SessionService,
    TurnService,
)
from gateway.features.conversation.domain import SessionNotFoundError
from gateway.features.conversation.infrastructure.repository import (
    SQLSessionRepository,
)
from gateway.features.conversation.infrastructure.turn_lease import SQLTurnLease
from gateway.features.conversation.presentation.rpc.handler import (
    ConversationRpcMethods,
)
from gateway.features.conversation.presentation.rpc.schemas import (
    CreateSessionParams,
    OpenSessionParams,
    SessionChannel,
    SessionParams,
    SessionSnapshotResponse,
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


class _DiscardingPublisher(EventPublisher):
    async def publish(self, event: ConversationEvent) -> None:
        pass


@pytest.fixture
def methods(
    session_repository: SQLSessionRepository,
    session_factory: async_sessionmaker[AsyncSession],
) -> ConversationRpcMethods:
    sessions = SessionService(session_repository)
    turns = TurnService(
        session_repository,
        sessions,
        SQLTurnLease(session_factory),
        _DiscardingPublisher(),
        _NullAgentRunner(),
    )
    return ConversationRpcMethods(sessions, turns)


async def test_create_session_persists_the_session(
    methods: ConversationRpcMethods,
    session_repository: SQLSessionRepository,
) -> None:
    response = await methods.create_session(CreateSessionParams(channel=_CHANNEL))

    assert response.channel == _CHANNEL
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


async def test_get_session_returns_a_snapshot(
    methods: ConversationRpcMethods,
) -> None:
    created = await methods.create_session(CreateSessionParams(channel=_CHANNEL))

    snapshot = await methods.get_session(SessionParams(session_id=created.id))

    assert isinstance(snapshot, SessionSnapshotResponse)
    assert snapshot.session.id == created.id


async def test_get_session_raises_for_an_unknown_session(
    methods: ConversationRpcMethods,
) -> None:
    with pytest.raises(SessionNotFoundError):
        await methods.get_session(SessionParams(session_id=uuid4()))
