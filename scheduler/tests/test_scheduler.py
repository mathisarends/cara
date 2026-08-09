import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

import pytest

from scheduler import (
    AtSchedule,
    CronSchedule,
    DuplicateJobError,
    EverySchedule,
    JobDefinition,
    JobRunner,
    Scheduler,
    SQLiteJobStore,
)

JOB_ID = UUID("00000000-0000-0000-0000-000000000123")
REMINDER_ID = UUID("00000000-0000-0000-0000-0000000000a1")
POLL_ID = UUID("00000000-0000-0000-0000-0000000000a2")


class RecordingRunner(JobRunner):
    def __init__(self) -> None:
        self.jobs: list[JobDefinition] = []
        self.called = asyncio.Event()

    async def run(self, job: JobDefinition) -> None:
        self.jobs.append(job)
        self.called.set()


def make_job(*, enabled: bool = True) -> JobDefinition:
    return JobDefinition(
        id=JOB_ID,
        name="Freitagszusammenfassung",
        schedule=CronSchedule(expression="0 18 * * 5", timezone="Europe/Berlin"),
        payload={"kind": "agent_prompt", "prompt": "Fasse meine Woche zusammen."},
        enabled=enabled,
    )


def test_manages_declarative_jobs(tmp_path: Path) -> None:
    asyncio.run(_assert_declarative_job_management(tmp_path / "jobs.sqlite"))


async def _assert_declarative_job_management(database_path: Path) -> None:
    scheduler = Scheduler(SQLiteJobStore(database_path), RecordingRunner())
    await scheduler.start()
    try:
        created = await scheduler.add(make_job())
        assert created.next_run_at is not None
        assert await scheduler.get(JOB_ID) == created

        disabled = await scheduler.disable(JOB_ID)
        assert disabled is not None
        assert disabled.enabled is False
        assert disabled.next_run_at is None
        assert await scheduler.list() == []
        assert await scheduler.list(include_disabled=True) == [disabled]

        enabled = await scheduler.enable(JOB_ID)
        assert enabled is not None
        assert enabled.enabled is True
        assert enabled.next_run_at is not None
        assert await scheduler.remove(JOB_ID) is True
        assert await scheduler.remove(JOB_ID) is False
    finally:
        await scheduler.shutdown()


def test_rejects_duplicate_id(tmp_path: Path) -> None:
    asyncio.run(_assert_duplicate_is_rejected(tmp_path / "jobs.sqlite"))


async def _assert_duplicate_is_rejected(database_path: Path) -> None:
    scheduler = Scheduler(SQLiteJobStore(database_path), RecordingRunner())
    await scheduler.start()
    try:
        await scheduler.add(make_job())
        with pytest.raises(DuplicateJobError, match=str(JOB_ID)):
            await scheduler.add(make_job())
    finally:
        await scheduler.shutdown()


def test_persists_job_across_restart(tmp_path: Path) -> None:
    asyncio.run(_assert_job_survives_restart(tmp_path / "jobs.sqlite"))


async def _assert_job_survives_restart(database_path: Path) -> None:
    first = Scheduler(SQLiteJobStore(database_path), RecordingRunner())
    await first.start()
    await first.add(make_job())
    await first.shutdown()

    second = Scheduler(SQLiteJobStore(database_path), RecordingRunner())
    await second.start()
    try:
        restored = await second.get(JOB_ID)
        assert restored is not None
        assert restored.schedule == make_job().schedule
        assert restored.next_run_at is not None
    finally:
        await second.shutdown()


def test_runs_job_immediately(tmp_path: Path) -> None:
    asyncio.run(_assert_job_runs_immediately(tmp_path / "jobs.sqlite"))


async def _assert_job_runs_immediately(database_path: Path) -> None:
    runner = RecordingRunner()
    scheduler = Scheduler(SQLiteJobStore(database_path), runner)
    await scheduler.start()
    try:
        await scheduler.add(make_job())
        assert await scheduler.run_now(JOB_ID) is True
        await asyncio.wait_for(runner.called.wait(), timeout=1)
        assert runner.jobs == [make_job()]
    finally:
        await scheduler.shutdown()


def test_one_shot_is_removed_after_success(tmp_path: Path) -> None:
    asyncio.run(_assert_one_shot_is_removed(tmp_path / "jobs.sqlite"))


async def _assert_one_shot_is_removed(database_path: Path) -> None:
    runner = RecordingRunner()
    scheduler = Scheduler(SQLiteJobStore(database_path), runner)
    await scheduler.start()
    job = JobDefinition(
        id=REMINDER_ID,
        name="Reminder",
        schedule=AtSchedule(at=datetime.now(UTC) + timedelta(milliseconds=50)),
        payload={"kind": "agent_prompt", "prompt": "Erinnere mich."},
    )
    try:
        await scheduler.add(job)
        await asyncio.wait_for(runner.called.wait(), timeout=1)
        assert await scheduler.get(REMINDER_ID) is None
    finally:
        await scheduler.shutdown()


def test_every_schedule_has_next_run(tmp_path: Path) -> None:
    asyncio.run(_assert_every_schedule_has_next_run(tmp_path / "jobs.sqlite"))


async def _assert_every_schedule_has_next_run(database_path: Path) -> None:
    scheduler = Scheduler(SQLiteJobStore(database_path), RecordingRunner())
    await scheduler.start()
    job = JobDefinition(
        id=POLL_ID,
        name="Poll",
        schedule=EverySchedule(seconds=600),
        payload={"kind": "agent_prompt", "prompt": "Prüfe den Status."},
    )
    try:
        created = await scheduler.add(job)
        assert created.next_run_at is not None
    finally:
        await scheduler.shutdown()
