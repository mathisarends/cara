import json
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast
from zoneinfo import ZoneInfo

import aiosqlite

from scheduler.models import At, Cron, Interval, ScheduledJob, Trigger
from scheduler.ports import Codec

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS scheduler_jobs (
    id TEXT PRIMARY KEY,
    name TEXT,
    trigger_kind TEXT NOT NULL,
    trigger_data TEXT NOT NULL,
    payload TEXT NOT NULL,
    created_at TEXT NOT NULL,
    next_run_at TEXT NOT NULL
)
"""


class SqliteJobStore[PayloadT]:
    def __init__(
        self,
        database: str | Path,
        *,
        payload_codec: Codec[PayloadT],
    ) -> None:
        self._database = database
        self._payload_codec = payload_codec

    async def add(self, job: ScheduledJob[PayloadT]) -> None:
        query = """
        INSERT INTO scheduler_jobs (
            id, name, trigger_kind, trigger_data, payload, created_at, next_run_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """
        async with self._connection() as connection:
            try:
                await connection.execute(query, _job_values(job, self._payload_codec))
                await connection.commit()
            except aiosqlite.IntegrityError as error:
                raise ValueError(f"Job {job.id!r} already exists") from error

    async def update(self, job: ScheduledJob[PayloadT]) -> None:
        query = """
        UPDATE scheduler_jobs
        SET name = ?,
            trigger_kind = ?,
            trigger_data = ?,
            payload = ?,
            created_at = ?,
            next_run_at = ?
        WHERE id = ?
        """
        values = _job_values(job, self._payload_codec)
        parameters = (*values[1:], values[0])
        async with self._connection() as connection:
            cursor = await connection.execute(query, parameters)
            if cursor.rowcount == 0:
                raise KeyError(f"Job {job.id!r} does not exist")
            await connection.commit()

    async def remove(self, job_id: str) -> bool:
        async with self._connection() as connection:
            cursor = await connection.execute(
                "DELETE FROM scheduler_jobs WHERE id = ?",
                (job_id,),
            )
            await connection.commit()
            return cursor.rowcount > 0

    async def get(self, job_id: str) -> ScheduledJob[PayloadT] | None:
        async with self._connection() as connection:
            cursor = await connection.execute(
                "SELECT * FROM scheduler_jobs WHERE id = ?",
                (job_id,),
            )
            row = await cursor.fetchone()
        if row is None:
            return None
        return _decode_job(row, self._payload_codec)

    async def list(self) -> tuple[ScheduledJob[PayloadT], ...]:
        async with self._connection() as connection:
            cursor = await connection.execute(
                "SELECT * FROM scheduler_jobs ORDER BY created_at, id"
            )
            rows = await cursor.fetchall()
        return tuple(_decode_job(row, self._payload_codec) for row in rows)

    @asynccontextmanager
    async def _connection(self) -> AsyncGenerator[aiosqlite.Connection]:
        async with aiosqlite.connect(self._database) as connection:
            connection.row_factory = aiosqlite.Row
            await connection.execute("PRAGMA busy_timeout = 5000")
            await connection.execute(_CREATE_TABLE)
            await connection.commit()
            yield connection


def _job_values[PayloadT](
    job: ScheduledJob[PayloadT],
    codec: Codec[PayloadT],
) -> tuple[str, str | None, str, str, str, str, str]:
    trigger_kind, trigger_data = _encode_trigger(job.trigger)
    return (
        job.id,
        job.name,
        trigger_kind,
        trigger_data,
        codec.encode(job.payload),
        job.created_at.astimezone(UTC).isoformat(),
        job.next_run_at.astimezone(UTC).isoformat(),
    )


def _decode_job[PayloadT](
    row: aiosqlite.Row,
    codec: Codec[PayloadT],
) -> ScheduledJob[PayloadT]:
    return ScheduledJob(
        id=cast(str, row["id"]),
        name=cast(str | None, row["name"]),
        trigger=_decode_trigger(
            cast(str, row["trigger_kind"]),
            cast(str, row["trigger_data"]),
        ),
        payload=codec.decode(cast(str, row["payload"])),
        created_at=datetime.fromisoformat(cast(str, row["created_at"])),
        next_run_at=datetime.fromisoformat(cast(str, row["next_run_at"])),
    )


def _encode_trigger(trigger: Trigger) -> tuple[str, str]:
    match trigger:
        case At(when=when):
            data = {"when": when.isoformat()}
            return "at", json.dumps(data, separators=(",", ":"), sort_keys=True)
        case Interval(every=every, run_immediately=run_immediately):
            data = {
                "run_immediately": run_immediately,
                "seconds": every.total_seconds(),
            }
            return "interval", json.dumps(data, separators=(",", ":"), sort_keys=True)
        case Cron(expression=expression, timezone=timezone):
            if isinstance(timezone, ZoneInfo):
                timezone_name = timezone.key
            elif timezone is UTC:
                timezone_name = "UTC"
            else:
                raise ValueError("Cron timezone must be UTC or an IANA timezone")
            data = {"expression": expression, "timezone": timezone_name}
            return "cron", json.dumps(data, separators=(",", ":"), sort_keys=True)


def _decode_trigger(kind: str, encoded: str) -> Trigger:
    data = cast(dict[str, object], json.loads(encoded))
    match kind:
        case "at":
            return At(when=datetime.fromisoformat(cast(str, data["when"])))
        case "interval":
            return Interval(
                every=timedelta(seconds=cast(float, data["seconds"])),
                run_immediately=cast(bool, data["run_immediately"]),
            )
        case "cron":
            return Cron(
                expression=cast(str, data["expression"]),
                timezone=ZoneInfo(cast(str, data["timezone"])),
            )
        case _:
            raise ValueError(f"Unknown trigger kind: {kind!r}")
