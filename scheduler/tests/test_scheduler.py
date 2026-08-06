import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from scheduler import (
    AgentPromptPayload,
    AtSchedule,
    CronSchedule,
    DuplicateJobError,
    EverySchedule,
    JobDefinition,
    NoDelivery,
    Scheduler,
)


class RecordingRunner:
    def __init__(self) -> None:
        self.jobs: list[JobDefinition] = []
        self.called = asyncio.Event()

    async def run(self, job: JobDefinition) -> None:
        self.jobs.append(job)
        self.called.set()


def make_job(*, enabled: bool = True) -> JobDefinition:
    return JobDefinition(
        id="job-123",
        name="Freitagszusammenfassung",
        schedule=CronSchedule(expression="0 18 * * 5", timezone="Europe/Berlin"),
        payload=AgentPromptPayload(prompt="Fasse meine Woche zusammen."),
        delivery=NoDelivery(),
        enabled=enabled,
    )


def test_manages_declarative_jobs(tmp_path: Path) -> None:
    asyncio.run(_assert_declarative_job_management(tmp_path / "jobs.sqlite"))


async def _assert_declarative_job_management(database_path: Path) -> None:
    scheduler = Scheduler(database_path, RecordingRunner())
    await scheduler.start()
    try:
        created = await scheduler.add(make_job())
        assert created.next_run_at is not None
        assert await scheduler.get("job-123") == created

        disabled = await scheduler.disable("job-123")
        assert disabled is not None
        assert disabled.enabled is False
        assert disabled.next_run_at is None
        assert await scheduler.list() == []
        assert await scheduler.list(include_disabled=True) == [disabled]

        enabled = await scheduler.enable("job-123")
        assert enabled is not None
        assert enabled.enabled is True
        assert enabled.next_run_at is not None
        assert await scheduler.remove("job-123") is True
        assert await scheduler.remove("job-123") is False
    finally:
        await scheduler.shutdown()


def test_rejects_duplicate_id(tmp_path: Path) -> None:
    asyncio.run(_assert_duplicate_is_rejected(tmp_path / "jobs.sqlite"))


async def _assert_duplicate_is_rejected(database_path: Path) -> None:
    scheduler = Scheduler(database_path, RecordingRunner())
    await scheduler.start()
    try:
        await scheduler.add(make_job())
        with pytest.raises(DuplicateJobError, match="job-123"):
            await scheduler.add(make_job())
    finally:
        await scheduler.shutdown()


def test_persists_job_across_restart(tmp_path: Path) -> None:
    asyncio.run(_assert_job_survives_restart(tmp_path / "jobs.sqlite"))


async def _assert_job_survives_restart(database_path: Path) -> None:
    first = Scheduler(database_path, RecordingRunner())
    await first.start()
    await first.add(make_job())
    await first.shutdown()

    second = Scheduler(database_path, RecordingRunner())
    await second.start()
    try:
        restored = await second.get("job-123")
        assert restored is not None
        assert restored.schedule == make_job().schedule
        assert restored.next_run_at is not None
    finally:
        await second.shutdown()


def test_runs_job_immediately(tmp_path: Path) -> None:
    asyncio.run(_assert_job_runs_immediately(tmp_path / "jobs.sqlite"))


async def _assert_job_runs_immediately(database_path: Path) -> None:
    runner = RecordingRunner()
    scheduler = Scheduler(database_path, runner)
    await scheduler.start()
    try:
        await scheduler.add(make_job())
        assert await scheduler.run_now("job-123") is True
        await asyncio.wait_for(runner.called.wait(), timeout=1)
        assert runner.jobs == [make_job()]
    finally:
        await scheduler.shutdown()


def test_one_shot_is_removed_after_success(tmp_path: Path) -> None:
    asyncio.run(_assert_one_shot_is_removed(tmp_path / "jobs.sqlite"))


async def _assert_one_shot_is_removed(database_path: Path) -> None:
    runner = RecordingRunner()
    scheduler = Scheduler(database_path, runner)
    await scheduler.start()
    job = JobDefinition(
        id="reminder",
        name="Reminder",
        schedule=AtSchedule(at=datetime.now(UTC) + timedelta(milliseconds=50)),
        payload=AgentPromptPayload(prompt="Erinnere mich."),
    )
    try:
        await scheduler.add(job)
        await asyncio.wait_for(runner.called.wait(), timeout=1)
        assert await scheduler.get("reminder") is None
    finally:
        await scheduler.shutdown()


def test_every_schedule_has_next_run(tmp_path: Path) -> None:
    asyncio.run(_assert_every_schedule_has_next_run(tmp_path / "jobs.sqlite"))


async def _assert_every_schedule_has_next_run(database_path: Path) -> None:
    scheduler = Scheduler(database_path, RecordingRunner())
    await scheduler.start()
    job = JobDefinition(
        id="poll",
        name="Poll",
        schedule=EverySchedule(seconds=600),
        payload=AgentPromptPayload(prompt="Prüfe den Status."),
    )
    try:
        created = await scheduler.add(job)
        assert created.next_run_at is not None
    finally:
        await scheduler.shutdown()
