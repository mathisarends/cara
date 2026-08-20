import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pytest

from scheduler import At, Cron, Interval, ScheduledRun, Scheduler


@dataclass(frozen=True, slots=True)
class Payload:
    value: str


def test_registers_all_supported_trigger_types() -> None:
    async def runner(run: ScheduledRun[Payload]) -> None:
        pass

    scheduler = Scheduler[Payload](runner)

    interval = scheduler.interval(
        every=timedelta(minutes=5),
        payload=Payload("check in"),
        job_id="interval",
    )
    at = scheduler.at(
        datetime(2026, 8, 21, 9, tzinfo=UTC),
        payload=Payload("one time"),
        job_id="at",
    )
    cron = scheduler.cron(
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
    assert scheduler.jobs == (interval, at, cron)


def test_schedule_accepts_a_trigger_directly() -> None:
    async def runner(run: ScheduledRun[str]) -> None:
        pass

    scheduler = Scheduler[str](runner)
    trigger = Interval(every=timedelta(minutes=10))

    job = scheduler.schedule(trigger=trigger, payload="payload")

    assert job.trigger is trigger
    assert job.payload == "payload"


def test_rejects_invalid_definitions() -> None:
    async def runner(run: ScheduledRun[str]) -> None:
        pass

    scheduler = Scheduler[str](runner)

    with pytest.raises(ValueError, match="greater than zero"):
        scheduler.interval(every=timedelta(0), payload="payload")
    with pytest.raises(ValueError, match="timezone"):
        scheduler.at(datetime(2026, 8, 21, 9), payload="payload")
    with pytest.raises(ValueError, match="five-field"):
        scheduler.cron(expression="not a cron", payload="payload")


def test_runs_at_job_once_with_typed_payload() -> None:
    async def scenario() -> None:
        runs: list[ScheduledRun[Payload]] = []
        called = asyncio.Event()

        async def runner(run: ScheduledRun[Payload]) -> None:
            runs.append(run)
            called.set()

        payload = Payload("stand up")
        scheduler = Scheduler[Payload](runner)
        job = scheduler.at(
            datetime.now(UTC) + timedelta(milliseconds=10),
            payload=payload,
        )

        async with scheduler:
            await asyncio.wait_for(called.wait(), timeout=1)
            await asyncio.sleep(0.02)

        assert len(runs) == 1
        assert scheduler.jobs == ()
        assert runs[0].job_id == job.id
        assert runs[0].payload is payload
        assert runs[0].scheduled_for.tzinfo is UTC

    asyncio.run(scenario())


def test_interval_continues_after_runner_failure() -> None:
    async def scenario() -> None:
        attempts = 0
        completed = asyncio.Event()
        errors: list[tuple[str, str]] = []

        async def runner(run: ScheduledRun[str]) -> None:
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise RuntimeError("temporary failure")
            completed.set()

        async def handle_error(job, error: Exception) -> None:
            errors.append((job.id, str(error)))

        scheduler = Scheduler[str](runner, error_handler=handle_error)
        job = scheduler.interval(
            every=timedelta(milliseconds=10),
            payload="payload",
        )

        async with scheduler:
            await asyncio.wait_for(completed.wait(), timeout=1)

        assert attempts == 2
        assert errors == [(job.id, "temporary failure")]

    asyncio.run(scenario())


def test_can_add_and_remove_job_while_running() -> None:
    async def scenario() -> None:
        called = asyncio.Event()

        async def runner(run: ScheduledRun[str]) -> None:
            called.set()

        scheduler = Scheduler[str](runner)
        await scheduler.start()
        try:
            job = scheduler.interval(
                every=timedelta(hours=1),
                payload="payload",
                run_immediately=False,
            )
            assert scheduler.remove(job.id)
            assert not scheduler.remove(job.id)
            await asyncio.sleep(0)
            assert not called.is_set()
        finally:
            await scheduler.stop()

    asyncio.run(scenario())
