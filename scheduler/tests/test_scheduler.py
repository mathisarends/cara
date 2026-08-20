import asyncio
from datetime import UTC, datetime, timedelta

import pytest

from scheduler import AgentRunRequest, Cron, Heartbeat, Reminder, Scheduler


def test_registers_all_supported_job_types() -> None:
    async def runner(request: AgentRunRequest) -> None:
        pass

    scheduler = Scheduler(runner)

    heartbeat = scheduler.heartbeat(
        "assistant",
        every=timedelta(minutes=5),
        payload={"prompt": "check in"},
        job_id="heartbeat",
    )
    reminder = scheduler.reminder(
        "assistant",
        at=datetime(2026, 8, 21, 9, tzinfo=UTC),
        job_id="reminder",
    )
    cron = scheduler.cron(
        "assistant",
        expression="0 7 * * 1-5",
        timezone="Europe/Berlin",
        job_id="cron",
    )

    assert heartbeat.kind == "heartbeat"
    assert isinstance(heartbeat.trigger, Heartbeat)
    assert reminder.kind == "reminder"
    assert isinstance(reminder.trigger, Reminder)
    assert cron.kind == "cron"
    assert isinstance(cron.trigger, Cron)
    assert scheduler.jobs == (heartbeat, reminder, cron)


def test_rejects_invalid_definitions() -> None:
    async def runner(request: AgentRunRequest) -> None:
        pass

    scheduler = Scheduler(runner)

    with pytest.raises(ValueError, match="greater than zero"):
        scheduler.heartbeat("assistant", every=timedelta(0))
    with pytest.raises(ValueError, match="timezone"):
        scheduler.reminder("assistant", at=datetime(2026, 8, 21, 9))
    with pytest.raises(ValueError, match="exactly one"):
        scheduler.reminder("assistant")
    with pytest.raises(ValueError, match="five-field"):
        scheduler.cron("assistant", expression="not a cron")


def test_runs_reminder_once_and_keeps_payload_immutable() -> None:
    async def scenario() -> None:
        requests: list[AgentRunRequest] = []
        called = asyncio.Event()

        async def runner(request: AgentRunRequest) -> None:
            requests.append(request)
            called.set()

        payload = {"prompt": "stand up"}
        scheduler = Scheduler(runner)
        job = scheduler.reminder(
            "assistant",
            after=timedelta(milliseconds=10),
            payload=payload,
        )
        payload["prompt"] = "changed"

        async with scheduler:
            await asyncio.wait_for(called.wait(), timeout=1)
            await asyncio.sleep(0.02)

        assert len(requests) == 1
        assert scheduler.jobs == ()
        assert requests[0].job_id == job.id
        assert requests[0].payload == {"prompt": "stand up"}
        assert requests[0].scheduled_for.tzinfo is UTC

    asyncio.run(scenario())


def test_heartbeat_continues_after_runner_failure() -> None:
    async def scenario() -> None:
        attempts = 0
        completed = asyncio.Event()
        errors: list[tuple[str, str]] = []

        async def runner(request: AgentRunRequest) -> None:
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise RuntimeError("temporary failure")
            completed.set()

        async def handle_error(job, error: Exception) -> None:
            errors.append((job.id, str(error)))

        scheduler = Scheduler(runner, error_handler=handle_error)
        job = scheduler.heartbeat(
            "assistant",
            every=timedelta(milliseconds=10),
        )

        async with scheduler:
            await asyncio.wait_for(completed.wait(), timeout=1)

        assert attempts == 2
        assert errors == [(job.id, "temporary failure")]

    asyncio.run(scenario())


def test_can_add_and_remove_job_while_running() -> None:
    async def scenario() -> None:
        called = asyncio.Event()

        async def runner(request: AgentRunRequest) -> None:
            called.set()

        scheduler = Scheduler(runner)
        await scheduler.start()
        try:
            job = scheduler.heartbeat(
                "assistant",
                every=timedelta(hours=1),
                run_immediately=False,
            )
            assert scheduler.remove(job.id)
            assert not scheduler.remove(job.id)
            await asyncio.sleep(0)
            assert not called.is_set()
        finally:
            await scheduler.stop()

    asyncio.run(scenario())
