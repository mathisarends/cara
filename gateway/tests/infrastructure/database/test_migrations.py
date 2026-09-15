from pathlib import Path

from sqlalchemy import create_engine, inspect
from sqlalchemy.ext.asyncio import create_async_engine

from gateway.platform.database.migrations import run_migrations


async def test_alembic_migrates_an_empty_database_to_head(tmp_path: Path) -> None:
    database_path = tmp_path / "gateway.sqlite3"
    async_engine = create_async_engine(
        f"sqlite+aiosqlite:///{database_path.as_posix()}"
    )
    try:
        await run_migrations(async_engine)
    finally:
        await async_engine.dispose()

    engine = create_engine(f"sqlite:///{database_path.as_posix()}")
    try:
        inspector = inspect(engine)
        tables = set(inspector.get_table_names())
        session_columns = {
            column["name"] for column in inspector.get_columns("gateway_sessions")
        }
        session_indexes = {
            index["name"] for index in inspector.get_indexes("gateway_sessions")
        }
    finally:
        engine.dispose()

    assert {
        "alembic_version",
        "gateway_automations",
        "gateway_sessions",
        "gateway_session_assistant_messages",
        "gateway_session_tool_call_sequences",
        "gateway_session_tool_calls",
        "gateway_session_user_messages",
    } <= tables
    assert {
        "channel_name",
        "channel_account_id",
    } <= session_columns
    assert "ix_gateway_sessions_channel" in session_indexes
