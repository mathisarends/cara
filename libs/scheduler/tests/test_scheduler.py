import asyncio
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from scheduler import At, Cron, Interval, ScheduledRun, Scheduler, first_run


def test_rejects_invalid_definitions() -> None:
    async def runner(run: ScheduledRun[str]) -> None:
        pass

    with pytest.raises(ValueError, match="greater than zero"):
        Interval(timedelta(0))
    with pytest.raises(ValueError, match="timezone"):
        At(datetime(2026, 8, 21, 9))
    with pytest.raises(ValueError, match="five-field"):
        Cron("not a cron", UTC)
    with pytest.raises(ValueError, match="timezone"):
        Scheduler[str](runner).schedule(
            "naive",
            trigger=Interval(timedelta(hours=1)),
            payload="payload",
            next_run_at=datetime(2026, 8, 21, 9),
        )


def test_first_run_covers_every_trigger() -> None:
    now = datetime(2026, 8, 21, 6, tzinfo=UTC)
    run_at = datetime(2026, 8, 21, 9, tzinfo=UTC)

    assert first_run(At(run_at), now) == run_at
    assert first_run(Interval(timedelta(minutes=5)), now) == now
    assert first_run(
        Interval(timedelta(minutes=5), run_immediately=False), now
    ) == now + timedelta(minutes=5)
    assert first_run(Cron("0 9 * * *", ZoneInfo("Europe/Berlin")), now) == datetime(
        2026, 8, 21, 7, tzinfo=UTC
    )


def test_runs_an_at_job_once_and_reports_no_next_run() -> None:
    async def scenario() -> None:
        runs: list[ScheduledRun[str]] = []
        called = asyncio.Event()

        async def runner(run: ScheduledRun[str]) -> None:
            runs.append(run)
            called.set()

        scheduler = Scheduler[str](runner)
        when = datetime.now(UTC) + timedelta(milliseconds=10)
        scheduler.schedule("once", trigger=At(when), payload="stand up")

        await scheduler.start()
        try:
            await asyncio.wait_for(called.wait(), timeout=1)
            await asyncio.sleep(0.02)
        finally:
            await scheduler.stop()

        assert runs == [
            ScheduledRun(
                job_id="once",
                scheduled_for=when,
                next_run_at=None,
                payload="stand up",
            )
        ]

    asyncio.run(scenario())


def test_resumes_at_a_persisted_next_run_and_reports_the_following_one() -> None:
    async def scenario() -> None:
        received: asyncio.Future[ScheduledRun[str]] = (
            asyncio.get_running_loop().create_future()
        )

        async def runner(run: ScheduledRun[str]) -> None:
            if not received.done():
                received.set_result(run)

        scheduler = Scheduler[str](runner)
        next_run_at = datetime.now(UTC) + timedelta(milliseconds=20)
        scheduler.schedule(
            "persisted",
            trigger=Interval(timedelta(hours=1), run_immediately=False),
            payload="payload",
            next_run_at=next_run_at,
        )

        await scheduler.start()
        try:
            run = await asyncio.wait_for(received, timeout=1)
        finally:
            await scheduler.stop()

        assert run.scheduled_for == next_run_at
        assert run.next_run_at == next_run_at + timedelta(hours=1)

    asyncio.run(scenario())


def test_a_persisted_run_in_the_past_fires_immediately() -> None:
    async def scenario() -> None:
        called = asyncio.Event()

        async def runner(run: ScheduledRun[str]) -> None:
            called.set()

        scheduler = Scheduler[str](runner)
        scheduler.schedule(
            "missed",
            trigger=Cron("0 9 * * *", UTC),
            payload="payload",
            next_run_at=datetime.now(UTC) - timedelta(hours=1),
        )

        await scheduler.start()
        try:
            await asyncio.wait_for(called.wait(), timeout=1)
        finally:
            await scheduler.stop()

    asyncio.run(scenario())


def test_schedule_replaces_a_job_with_the_same_id() -> None:
    async def scenario() -> None:
        runs: list[ScheduledRun[str]] = []
        called = asyncio.Event()

        async def runner(run: ScheduledRun[str]) -> None:
            runs.append(run)
            called.set()

        scheduler = Scheduler[str](runner)
        scheduler.schedule(
            "job",
            trigger=Interval(timedelta(hours=1), run_immediately=False),
            payload="original",
        )

        await scheduler.start()
        try:
            scheduler.schedule(
                "job",
                trigger=Interval(timedelta(hours=1), run_immediately=True),
                payload="updated",
            )
            await asyncio.wait_for(called.wait(), timeout=1)
        finally:
            await scheduler.stop()

        assert [run.payload for run in runs] == ["updated"]

    asyncio.run(scenario())


def test_removed_jobs_never_run() -> None:
    async def scenario() -> None:
        called = asyncio.Event()

        async def runner(run: ScheduledRun[str]) -> None:
            called.set()

        scheduler = Scheduler[str](runner)
        scheduler.schedule(
            "job",
            trigger=Interval(timedelta(hours=1), run_immediately=True),
            payload="payload",
        )
        scheduler.remove("job")

        await scheduler.start()
        try:
            await asyncio.sleep(0.02)
        finally:
            await scheduler.stop()

        assert not called.is_set()

    asyncio.run(scenario())


def test_runner_failures_do_not_stop_recurring_jobs() -> None:
    async def scenario() -> None:
        attempts = 0
        second_attempt = asyncio.Event()

        async def runner(run: ScheduledRun[str]) -> None:
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise RuntimeError("boom")
            second_attempt.set()

        scheduler = Scheduler[str](runner)
        scheduler.schedule(
            "flaky",
            trigger=Interval(timedelta(milliseconds=10), run_immediately=True),
            payload="payload",
        )

        await scheduler.start()
        try:
            await asyncio.wait_for(second_attempt.wait(), timeout=1)
        finally:
            await scheduler.stop()

    asyncio.run(scenario())
