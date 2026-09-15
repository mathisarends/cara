from collections.abc import AsyncIterator

import pytest
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel

from gateway.features.conversation.infrastructure.repository import (
    SQLSessionRepository,
)


@pytest.fixture
async def async_engine() -> AsyncIterator[AsyncEngine]:
    # StaticPool keeps every connection on the same in-memory database; without
    # it, concurrent connections (e.g. a background turn task racing the test's
    # own queries) would each see a separate, table-less :memory: database.
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
    )
    async with engine.begin() as connection:
        await connection.run_sync(SQLModel.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest.fixture
def session_factory(
    async_engine: AsyncEngine,
) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(async_engine, expire_on_commit=False)


@pytest.fixture
def session_repository(
    session_factory: async_sessionmaker[AsyncSession],
) -> SQLSessionRepository:
    return SQLSessionRepository(session_factory)
