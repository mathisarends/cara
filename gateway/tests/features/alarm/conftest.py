import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from features.alarm.fakes import AcceptAllTargets, FixedClock, RecordingScheduler
from gateway.features.alarm.application import AlarmService, AlarmStore
from gateway.features.alarm.infrastructure.repository import SQLAlarmRepository


@pytest.fixture
def alarm_repository(
    session_factory: async_sessionmaker[AsyncSession],
) -> SQLAlarmRepository:
    return SQLAlarmRepository(session_factory)


@pytest.fixture
def clock() -> FixedClock:
    return FixedClock()


@pytest.fixture
def recording_scheduler() -> RecordingScheduler:
    return RecordingScheduler()


@pytest.fixture
def alarm_store(
    alarm_repository: SQLAlarmRepository,
    recording_scheduler: RecordingScheduler,
) -> AlarmStore:
    return AlarmStore(alarm_repository, recording_scheduler)


@pytest.fixture
def alarm_service(alarm_store: AlarmStore, clock: FixedClock) -> AlarmService:
    return AlarmService(alarm_store, AcceptAllTargets(), clock)
