from collections.abc import AsyncGenerator
from pathlib import Path

import pytest
from dishka import AsyncContainer, make_async_container
from dishka.integrations.fastapi import FastapiProvider
from sqlalchemy import event, text
from sqlalchemy.engine.interfaces import DBAPIConnection
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.pool import ConnectionPoolEntry

from gateway.platform.database import DatabaseProvider


@pytest.fixture
async def database_container(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> AsyncGenerator[AsyncContainer]:
    database_path = tmp_path / "scope.sqlite3"
    monkeypatch.setenv(
        "DATABASE_URL", f"sqlite+aiosqlite:///{database_path.as_posix()}"
    )
    database_provider = DatabaseProvider()
    fastapi_provider = FastapiProvider()
    container = make_async_container(database_provider, fastapi_provider)
    try:
        engine = await container.get(AsyncEngine)

        @event.listens_for(engine.sync_engine, "connect")
        def enable_foreign_keys(
            connection: DBAPIConnection, _record: ConnectionPoolEntry
        ) -> None:
            cursor = connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

        async with engine.begin() as connection:
            parent_table = text("CREATE TABLE scope_parents (id INTEGER PRIMARY KEY)")
            note_table = text(
                "CREATE TABLE scope_notes (text TEXT NOT NULL, parent_id INTEGER "
                "REFERENCES scope_parents(id) DEFERRABLE INITIALLY DEFERRED)"
            )
            await connection.execute(parent_table)
            await connection.execute(note_table)
        yield container
    finally:
        await container.close()
