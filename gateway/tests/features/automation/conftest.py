from collections.abc import AsyncIterator

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from features.automation.fakes import (
    AcceptAllTargets,
    ImmediateTransaction,
    RecordingScheduler,
)
from gateway.features.automation.application import AutomationService
from gateway.features.automation.infrastructure.repository import (
    SQLAutomationRepository,
)


@pytest.fixture
async def automation_session(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncSession]:
    async with session_factory() as session:
        yield session
        await session.rollback()


@pytest.fixture
def automation_repository(
    automation_session: AsyncSession,
) -> SQLAutomationRepository:
    return SQLAutomationRepository(automation_session)


@pytest.fixture
def recording_scheduler() -> RecordingScheduler:
    return RecordingScheduler()


@pytest.fixture
def automation_service(
    automation_repository: SQLAutomationRepository,
    recording_scheduler: RecordingScheduler,
) -> AutomationService:
    return AutomationService(
        automation_repository,
        AcceptAllTargets(),
        recording_scheduler,
        ImmediateTransaction(),
    )
