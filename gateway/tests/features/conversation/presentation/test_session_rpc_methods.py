import asyncio
from uuid import uuid4

import pytest

from gateway.features.conversation.application import SessionService
from gateway.features.conversation.domain import SessionNotFoundError
from gateway.features.conversation.infrastructure.repository import (
    SQLSessionRepository,
)
from gateway.features.conversation.presentation.rpc.methods import (
    create_session,
    get_session,
    open_session,
)
from gateway.features.conversation.presentation.rpc.models import (
    CreateSessionParams,
    OpenSessionParams,
    SessionChannel,
    SessionParams,
    SessionSnapshotResponse,
)

_CHANNEL = SessionChannel(name="voice")


@pytest.fixture
def sessions(session_repository: SQLSessionRepository) -> SessionService:
    return SessionService(session_repository)


async def test_create_session_persists_the_session(
    sessions: SessionService,
    session_repository: SQLSessionRepository,
) -> None:
    response = await create_session(CreateSessionParams(channel=_CHANNEL), sessions)

    assert response.channel == _CHANNEL
    assert await session_repository.find_by_id(response.id) is not None


async def test_create_session_always_creates_a_fresh_session(
    sessions: SessionService,
) -> None:
    first = await create_session(CreateSessionParams(channel=_CHANNEL), sessions)
    second = await create_session(CreateSessionParams(channel=_CHANNEL), sessions)

    assert second.id != first.id


async def test_open_session_reuses_the_latest_session_for_the_channel(
    sessions: SessionService,
) -> None:
    created = await create_session(CreateSessionParams(channel=_CHANNEL), sessions)

    opened = await open_session(OpenSessionParams(channel=_CHANNEL), sessions)

    assert opened.id == created.id


async def test_concurrent_open_session_calls_resolve_to_one_session(
    sessions: SessionService,
) -> None:
    first, second = await asyncio.gather(
        open_session(OpenSessionParams(channel=_CHANNEL), sessions),
        open_session(OpenSessionParams(channel=_CHANNEL), sessions),
    )

    assert second.id == first.id


async def test_open_session_does_not_cross_channel_boundaries(
    sessions: SessionService,
) -> None:
    first = await open_session(OpenSessionParams(channel=_CHANNEL), sessions)

    second = await open_session(
        OpenSessionParams(channel=SessionChannel(name="cli")),
        sessions,
    )

    assert second.id != first.id


async def test_get_session_returns_a_snapshot(
    sessions: SessionService,
) -> None:
    created = await create_session(CreateSessionParams(channel=_CHANNEL), sessions)

    snapshot = await get_session(SessionParams(session_id=created.id), sessions)

    assert isinstance(snapshot, SessionSnapshotResponse)
    assert snapshot.session.id == created.id


async def test_get_session_raises_for_an_unknown_session(
    sessions: SessionService,
) -> None:
    with pytest.raises(SessionNotFoundError):
        await get_session(SessionParams(session_id=uuid4()), sessions)
