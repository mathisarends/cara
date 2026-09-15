from collections.abc import AsyncIterator

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from gateway.features.conversation.application import TurnLease
from gateway.features.conversation.domain import SessionRepository
from gateway.features.conversation.infrastructure.repository import (
    SQLSessionRepository,
)
from gateway.features.conversation.infrastructure.turn_lease import SQLTurnLease
from gateway.shared import UnitOfWork


@pytest.fixture
async def session_repository(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[SQLSessionRepository]:
    async with session_factory() as session:
        yield SQLSessionRepository(session)


@pytest.fixture
def session_units(make_unit_of_work) -> UnitOfWork[SessionRepository]:
    return make_unit_of_work(SQLSessionRepository)


@pytest.fixture
def lease_units(make_unit_of_work) -> UnitOfWork[TurnLease]:
    return make_unit_of_work(SQLTurnLease)
