import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from gateway.features.conversation.infrastructure.repository import (
    SQLSessionRepository,
)


@pytest.fixture
def session_repository(
    session_factory: async_sessionmaker[AsyncSession],
) -> SQLSessionRepository:
    return SQLSessionRepository(session_factory)
