import asyncio
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta

import pytest

from scheduler import (
    At,
    Cron,
    Interval,
    MemoryJobStore,
    ScheduledJob,
    ScheduledRun,
    Scheduler,
)


@dataclass(frozen=True, slots=True)
class Payload:
    value: str


def test_memory_store_supports_crud() -> None:
    async def scenario() -> None:
        store = MemoryJobStore[Payload]()
        now = datetime.now(UTC)
        job = ScheduledJob(
            id="job",
            trigger=Interval(timedelta(minutes=5)),
            payload=Payload("original"),
            created_at=now,
            next_run_at=now,
        )

        await store.add(job)
        assert await store.get(job.id) == job
        assert await store.list() == (job,)

        updated = replace(job, payload=Payload("updated"))
        await store.update(updated)
        assert await store.get(job.id) == updated
        assert await store.remove(job.id)
        assert not await store.remove(job.id)
        assert await store.list() == ()

    asyncio.run(scenario())


def test_memory_store_rejects_duplicate_and_missing_updates() -> None:
    async def scenario() -> None:
        store = MemoryJobStore[str]()
        now = datetime.now(UTC)
        job = ScheduledJob(
            id="job",
            trigger=At(now),
            payload="payload",
            created_at=now,
            next_run_at=now,
        )

        await store.add(job)
        with pytest.raises(ValueError, match="already exists"):
            await store.add(job)
        await store.remove(job.id)
        with pytest.raises(KeyError, match="does not exist"):
            await store.update(job)

    asyncio.run(scenario())


def test_registers_all_supported_trigger_types() -> None:
    async def scenario() -> None:
        async def runner(run: ScheduledRun[Payload]) -> None:
            pass

        store = MemoryJobStore[Payload]()
        scheduler = Scheduler(runner, store)

        interval = await scheduler.interval(
            every=timedelta(minutes=5),
            payload=Payload("check in"),
            job_id="interval",
        )
        at = await scheduler.at(
            datetime(2026, 8, 21, 9, tzinfo=UTC),
            payload=Payload("one time"),
            job_id="at",
        )
        cron = await scheduler.cron(
            expression="0 7 * * 1-5",
            timezone="Europe/Berlin",
            payload=Payload("weekday"),
            job_id="cron",
        )

        assert interval.kind == "interval"
        assert isinstance(interval.trigger, Interval)
        assert at.kind == "at"
        assert isinstance(at.trigger, At)
        assert cron.kind == "cron"
        assert isinstance(cron.trigger, Cron)
        assert await store.list() == (interval, at, cron)

    asyncio.run(scenario())


def test_scheduler_exposes_persisted_jobs_for_management() -> None:
    async def scenario() -> None:
        async def runner(run: ScheduledRun[str]) -> None:
            pass

        scheduler = Scheduler(runner, MemoryJobStore[str]())
        job = await scheduler.at(
            datetime(2026, 8, 21, 9, tzinfo=UTC),
            payload="payload",
            job_id="managed",
        )

        assert await scheduler.get(job.id) == job
        assert await scheduler.list() == (job,)
        assert await scheduler.get("missing") is None

    asyncio.run(scenario())


def test_rejects_invalid_definitions() -> None:
    async def scenario() -> None:
        async def runner(run: ScheduledRun[str]) -> None:
            pass

        scheduler = Scheduler(runner, MemoryJobStore())

        with pytest.raises(ValueError, match="greater than zero"):
            await scheduler.interval(every=timedelta(0), payload="payload")
        with pytest.raises(ValueError, match="timezone"):
            await scheduler.at(datetime(2026, 8, 21, 9), payload="payload")
        with pytest.raises(ValueError, match="five-field"):
            await scheduler.cron(expression="not a cron", payload="payload")

    asyncio.run(scenario())


def test_runs_at_job_once_and_removes_it_from_store() -> None:
    async def scenario() -> None:
        runs: list[ScheduledRun[Payload]] = []
        called = asyncio.Event()

        async def runner(run: ScheduledRun[Payload]) -> None:
            runs.append(run)
            called.set()

        store = MemoryJobStore[Payload]()
        scheduler = Scheduler(runner, store)
        payload = Payload("stand up")
        job = await scheduler.at(
            datetime.now(UTC) + timedelta(milliseconds=10),
            payload=payload,
        )

        async with scheduler:
            await asyncio.wait_for(called.wait(), timeout=1)
            await asyncio.sleep(0.02)

        assert len(runs) == 1
        assert await store.list() == ()
        assert runs[0].job_id == job.id
        assert runs[0].payload is payload

    asyncio.run(scenario())


def test_start_loads_jobs_and_preserves_interval_anchor() -> None:
    async def scenario() -> None:
        store = MemoryJobStore[str]()
        now = datetime.now(UTC)
        next_run_at = now + timedelta(milliseconds=20)
        job = ScheduledJob(
            id="persisted",
            trigger=Interval(timedelta(hours=1), run_immediately=False),
            payload="payload",
            created_at=now - timedelta(hours=2),
            next_run_at=next_run_at,
        )
        await store.add(job)
        received: asyncio.Future[ScheduledRun[str]] = (
            asyncio.get_running_loop().create_future()
        )

        async def runner(run: ScheduledRun[str]) -> None:
            received.set_result(run)

        scheduler = Scheduler(runner, store)
        async with scheduler:
            run = await asyncio.wait_for(received, timeout=1)

        persisted = await store.get(job.id)
        assert run.scheduled_for == next_run_at
        assert persisted is not None
        assert persisted.next_run_at == next_run_at + timedelta(hours=1)

    asyncio.run(scenario())


def test_can_add_and_remove_job_while_running() -> None:
    async def scenario() -> None:
        called = asyncio.Event()

        async def runner(run: ScheduledRun[str]) -> None:
            called.set()

        store = MemoryJobStore[str]()
        scheduler = Scheduler(runner, store)
        await scheduler.start()
        try:
            job = await scheduler.interval(
                every=timedelta(hours=1),
                payload="payload",
                run_immediately=False,
            )
            assert await scheduler.remove(job.id)
            assert not await scheduler.remove(job.id)
            await asyncio.sleep(0)
            assert not called.is_set()
        finally:
            await scheduler.stop()

    asyncio.run(scenario())


def test_update_replaces_the_trigger_of_a_running_job() -> None:
    async def scenario() -> None:
        runs: list[ScheduledRun[str]] = []
        called = asyncio.Event()

        async def runner(run: ScheduledRun[str]) -> None:
            runs.append(run)
            called.set()

        scheduler = Scheduler(runner, MemoryJobStore[str]())
        await scheduler.start()
        try:
            job = await scheduler.interval(
                every=timedelta(hours=1),
                payload="original",
                run_immediately=False,
            )
            updated = await scheduler.update(
                job.id,
                trigger=Interval(timedelta(hours=1), run_immediately=True),
                payload="updated",
                name="renamed",
            )

            assert updated is not None
            assert updated.created_at == job.created_at
            assert updated.payload == "updated"
            assert updated.name == "renamed"
            await asyncio.wait_for(called.wait(), timeout=1)
            assert [run.payload for run in runs] == ["updated"]
        finally:
            await scheduler.stop()

    asyncio.run(scenario())


def test_update_returns_none_for_an_unknown_job() -> None:
    async def scenario() -> None:
        async def runner(run: ScheduledRun[str]) -> None:
            pass

        scheduler = Scheduler(runner, MemoryJobStore[str]())

        assert (
            await scheduler.update(
                "missing",
                trigger=At(datetime(2027, 1, 1, tzinfo=UTC)),
                payload="payload",
            )
            is None
        )

    asyncio.run(scenario())
