from collections.abc import AsyncIterator

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from features.alarm.fakes import AcceptAllTargets, FixedClock, RecordingScheduler
from gateway.features.alarm.application import AlarmService, AlarmStore
from gateway.features.alarm.domain import AlarmRepository
from gateway.features.alarm.infrastructure.repository import SQLAlarmRepository
from gateway.shared import UnitOfWork


@pytest.fixture
async def alarm_repository(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[SQLAlarmRepository]:
    async with session_factory() as session:
        yield SQLAlarmRepository(session)


@pytest.fixture
def alarm_repositories(make_unit_of_work) -> UnitOfWork[AlarmRepository]:
    return make_unit_of_work(SQLAlarmRepository)


@pytest.fixture
def clock() -> FixedClock:
    return FixedClock()


@pytest.fixture
def recording_scheduler() -> RecordingScheduler:
    return RecordingScheduler()


@pytest.fixture
def alarm_store(
    alarm_repositories: UnitOfWork[AlarmRepository],
    recording_scheduler: RecordingScheduler,
) -> AlarmStore:
    return AlarmStore(alarm_repositories, recording_scheduler)


@pytest.fixture
def alarm_service(alarm_store: AlarmStore, clock: FixedClock) -> AlarmService:
    return AlarmService(alarm_store, AcceptAllTargets(), clock)
