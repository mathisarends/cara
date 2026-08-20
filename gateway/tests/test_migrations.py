import asyncio
from pathlib import Path

from sqlalchemy import create_engine, inspect
from sqlalchemy.ext.asyncio import create_async_engine

from gateway.infrastructure.database.migrations import run_migrations


def test_alembic_migrates_an_empty_database_to_head(tmp_path: Path) -> None:
    database_path = tmp_path / "gateway.sqlite3"

    asyncio.run(_migrate_database(database_path))

    engine = create_engine(f"sqlite:///{database_path.as_posix()}")
    try:
        tables = set(inspect(engine).get_table_names())
    finally:
        engine.dispose()

    assert {
        "alembic_version",
        "gateway_sessions",
        "gateway_session_assistant_messages",
        "gateway_session_tool_call_sequences",
        "gateway_session_tool_calls",
        "gateway_session_user_messages",
    } <= tables


async def _migrate_database(database_path: Path) -> None:
    async_engine = create_async_engine(
        f"sqlite+aiosqlite:///{database_path.as_posix()}"
    )
    try:
        await run_migrations(async_engine)
    finally:
        await async_engine.dispose()
