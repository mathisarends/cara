from datetime import UTC, datetime
from uuid import UUID

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlmodel import SQLModel

from gateway.features.scheduling.infrastructure import SQLiteJobStore
from gateway.infrastructure.database import ScheduledJobModel
from scheduler import AtSchedule, DuplicateJobError, JobDefinition

JOB_ID = UUID("00000000-0000-0000-0000-000000000123")


def _job(*, enabled: bool = True) -> JobDefinition:
    return JobDefinition(
        id=JOB_ID,
        name="Reminder",
        schedule=AtSchedule(at=datetime(2026, 8, 10, 9, tzinfo=UTC)),
        payload={"kind": "agent_prompt", "prompt": "Erinnere mich."},
        enabled=enabled,
    )


@pytest_asyncio.fixture
async def store() -> SQLiteJobStore:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(SQLModel.metadata.create_all)
    session_factory = async_sessionmaker(engine, class_=AsyncSession)
    yield SQLiteJobStore(session_factory)
    await engine.dispose()


@pytest.mark.asyncio
async def test_persists_and_restores_job(store: SQLiteJobStore) -> None:
    await store.add(_job(), replace_existing=False)

    assert await store.get(JOB_ID) == _job()
    assert await store.list() == [_job()]


@pytest.mark.asyncio
async def test_replaces_existing_job(store: SQLiteJobStore) -> None:
    await store.add(_job(), replace_existing=False)
    await store.add(_job(enabled=False), replace_existing=True)

    assert await store.get(JOB_ID) == _job(enabled=False)


@pytest.mark.asyncio
async def test_rejects_duplicate_job(store: SQLiteJobStore) -> None:
    await store.add(_job(), replace_existing=False)

    with pytest.raises(DuplicateJobError, match=str(JOB_ID)):
        await store.add(_job(), replace_existing=False)


@pytest.mark.asyncio
async def test_removes_job(store: SQLiteJobStore) -> None:
    await store.add(_job(), replace_existing=False)

    assert await store.remove(JOB_ID) is True
    assert await store.remove(JOB_ID) is False
    assert await store.get(JOB_ID) is None


def test_job_model_uses_gateway_table() -> None:
    assert ScheduledJobModel.__tablename__ == "gateway_scheduled_jobs"
