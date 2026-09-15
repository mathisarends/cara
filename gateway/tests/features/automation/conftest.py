import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from features.automation.fakes import AcceptAllTargets, RecordingScheduler
from gateway.features.automation.application import AutomationService
from gateway.features.automation.infrastructure.repository import (
    SQLAutomationRepository,
)


@pytest.fixture
def automation_repository(
    session_factory: async_sessionmaker[AsyncSession],
) -> SQLAutomationRepository:
    return SQLAutomationRepository(session_factory)


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
    )
