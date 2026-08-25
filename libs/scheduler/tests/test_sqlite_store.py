import asyncio
import json
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from scheduler import (
    At,
    Cron,
    Interval,
    ScheduledJob,
    ScheduledRun,
    Scheduler,
    SqliteJobStore,
)


@dataclass(frozen=True, slots=True)
class Payload:
    message: str


class JsonPayloadCodec:
    def encode(self, value: Payload) -> str:
        return json.dumps({"message": value.message})

    def decode(self, value: str) -> Payload:
        data = json.loads(value)
        return Payload(message=data["message"])


def test_sqlite_store_persists_crud_and_all_trigger_types(tmp_path: Path) -> None:
    async def scenario() -> None:
        database = tmp_path / "scheduler.db"
        codec = JsonPayloadCodec()
        store = SqliteJobStore(database, payload_codec=codec)
        now = datetime.now(UTC)
        jobs = (
            ScheduledJob(
                id="at",
                trigger=At(now + timedelta(hours=1)),
                payload=Payload("once"),
                created_at=now,
                next_run_at=now + timedelta(hours=1),
            ),
            ScheduledJob(
                id="interval",
                trigger=Interval(timedelta(minutes=30), run_immediately=False),
                payload=Payload("repeat"),
                created_at=now + timedelta(microseconds=1),
                next_run_at=now + timedelta(minutes=30),
                name="interval job",
            ),
            ScheduledJob(
                id="cron",
                trigger=Cron("0 8 * * *", ZoneInfo("Europe/Berlin")),
                payload=Payload("daily"),
                created_at=now + timedelta(microseconds=2),
                next_run_at=now + timedelta(days=1),
            ),
        )

        for job in jobs:
            await store.add(job)

        reopened = SqliteJobStore(database, payload_codec=codec)
        assert await reopened.list() == jobs
        assert await reopened.get("interval") == jobs[1]

        updated = replace(jobs[1], payload=Payload("updated"))
        await reopened.update(updated)
        assert await reopened.get(updated.id) == updated
        assert await reopened.remove("at")
        assert not await reopened.remove("missing")

        with pytest.raises(ValueError, match="already exists"):
            await reopened.add(updated)
        with pytest.raises(KeyError, match="does not exist"):
            await reopened.update(replace(updated, id="missing"))

    asyncio.run(scenario())


def test_scheduler_loads_job_from_reopened_sqlite_store(tmp_path: Path) -> None:
    async def scenario() -> None:
        database = tmp_path / "scheduler.db"
        codec = JsonPayloadCodec()

        async def unused_runner(run: ScheduledRun[Payload]) -> None:
            raise AssertionError("The first scheduler must not run")

        first = Scheduler(
            unused_runner,
            SqliteJobStore(database, payload_codec=codec),
        )
        job = await first.at(
            datetime.now(UTC) + timedelta(milliseconds=20),
            payload=Payload("survived restart"),
            job_id="persisted",
        )

        received: asyncio.Future[ScheduledRun[Payload]] = (
            asyncio.get_running_loop().create_future()
        )

        async def runner(run: ScheduledRun[Payload]) -> None:
            received.set_result(run)

        reopened_store = SqliteJobStore(database, payload_codec=codec)
        restarted = Scheduler(runner, reopened_store)
        async with restarted:
            run = await asyncio.wait_for(received, timeout=1)
            await asyncio.sleep(0.02)

        assert run.job_id == job.id
        assert run.payload == Payload("survived restart")
        assert await reopened_store.get(job.id) is None

    asyncio.run(scenario())
