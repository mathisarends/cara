import sqlite3
from pathlib import Path
from uuid import UUID

import aiosqlite

from scheduler.models import JobDefinition
from scheduler.store import DuplicateJobError, JobStore


class SQLiteJobStore(JobStore):
    """Adapter that persists job definitions to a local SQLite database."""

    def __init__(self, database_path: str | Path) -> None:
        self._database_path = str(database_path)
        self._connection: aiosqlite.Connection | None = None

    async def open(self) -> None:
        if self._connection is not None:
            return
        self._connection = await aiosqlite.connect(self._database_path)
        await self._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS scheduled_jobs (
                id TEXT PRIMARY KEY,
                definition TEXT NOT NULL
            )
            """
        )
        await self._connection.commit()

    async def close(self) -> None:
        if self._connection is not None:
            await self._connection.close()
            self._connection = None

    async def add(self, job: JobDefinition, *, replace_existing: bool) -> None:
        connection = self._require_connection()
        statement = (
            "INSERT OR REPLACE INTO scheduled_jobs (id, definition) VALUES (?, ?)"
            if replace_existing
            else "INSERT INTO scheduled_jobs (id, definition) VALUES (?, ?)"
        )
        try:
            await connection.execute(statement, (str(job.id), job.model_dump_json()))
            await connection.commit()
        except sqlite3.IntegrityError as error:
            raise DuplicateJobError(f"job already exists: {job.id}") from error

    async def get(self, job_id: UUID) -> JobDefinition | None:
        connection = self._require_connection()
        cursor = await connection.execute(
            "SELECT definition FROM scheduled_jobs WHERE id = ?", (str(job_id),)
        )
        row = await cursor.fetchone()
        await cursor.close()
        return JobDefinition.model_validate_json(row[0]) if row is not None else None

    async def list(self) -> list[JobDefinition]:
        connection = self._require_connection()
        cursor = await connection.execute(
            "SELECT definition FROM scheduled_jobs ORDER BY id"
        )
        rows = await cursor.fetchall()
        await cursor.close()
        return [JobDefinition.model_validate_json(row[0]) for row in rows]

    async def remove(self, job_id: UUID) -> bool:
        connection = self._require_connection()
        cursor = await connection.execute(
            "DELETE FROM scheduled_jobs WHERE id = ?", (str(job_id),)
        )
        await connection.commit()
        removed = cursor.rowcount > 0
        await cursor.close()
        return removed

    def _require_connection(self) -> aiosqlite.Connection:
        if self._connection is None:
            raise RuntimeError("job store is not open")
        return self._connection
