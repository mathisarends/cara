from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import Connection, create_engine, inspect, text
from sqlalchemy.ext.asyncio import create_async_engine

from gateway.platform.database.migrations import run_migrations

_GATEWAY_ROOT = Path(__file__).resolve().parents[3]


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
        automation_columns = {
            column["name"] for column in inspector.get_columns("gateway_automations")
        }
        alarm_indexes = {
            index["name"] for index in inspector.get_indexes("gateway_alarms")
        }
        alarm_columns = {
            column["name"] for column in inspector.get_columns("gateway_alarms")
        }
    finally:
        engine.dispose()

    assert {
        "alembic_version",
        "gateway_alarms",
        "gateway_automations",
        "gateway_sessions",
        "gateway_session_assistant_messages",
        "gateway_session_tool_call_sequences",
        "gateway_session_tool_calls",
        "gateway_session_user_messages",
    } <= tables
    assert "channel_name" in session_columns
    assert "inactivity_timeout_seconds" not in session_columns
    assert "is_current" in session_columns
    assert "channel_account_id" not in session_columns
    assert "ix_gateway_sessions_channel" in session_indexes
    assert "uq_gateway_sessions_current_channel" in session_indexes
    assert "created_from_turn_id" not in automation_columns
    assert "target_channel_name" in automation_columns
    assert "delivery_voice_room" in automation_columns
    assert "ix_gateway_alarms_owner_id" in alarm_indexes
    assert "delivery_voice_room" in alarm_columns


async def test_alembic_downgrades_alarms_and_the_automation_origin(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "gateway.sqlite3"
    async_engine = create_async_engine(
        f"sqlite+aiosqlite:///{database_path.as_posix()}"
    )
    try:
        await run_migrations(async_engine)
        async with async_engine.connect() as connection:
            await connection.run_sync(_downgrade, "0010")
    finally:
        await async_engine.dispose()

    engine = create_engine(f"sqlite:///{database_path.as_posix()}")
    try:
        inspector = inspect(engine)
        tables = set(inspector.get_table_names())
        automation_columns = {
            column["name"] for column in inspector.get_columns("gateway_automations")
        }
    finally:
        engine.dispose()

    assert "gateway_alarms" not in tables
    assert "created_from_turn_id" in automation_columns


async def test_current_session_migration_marks_only_the_latest_per_channel(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "gateway.sqlite3"
    database_url = f"sqlite+aiosqlite:///{database_path.as_posix()}"
    async_engine = create_async_engine(database_url)
    try:
        await run_migrations(async_engine)
        async with async_engine.connect() as connection:
            await connection.run_sync(_downgrade, "0016")
    finally:
        await async_engine.dispose()

    engine = create_engine(f"sqlite:///{database_path.as_posix()}")
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO gateway_sessions
                        (id, created_at, channel_name, turn_active)
                    VALUES
                        (:old_id, :old_time, 'web', false),
                        (:new_id, :new_time, 'web', false),
                        (:voice_id, :old_time, 'voice', false)
                    """
                ),
                {
                    "old_id": "00000000000000000000000000000001",
                    "new_id": "00000000000000000000000000000002",
                    "voice_id": "00000000000000000000000000000003",
                    "old_time": "2026-01-01 00:00:00",
                    "new_time": "2026-01-02 00:00:00",
                },
            )
    finally:
        engine.dispose()

    async_engine = create_async_engine(database_url)
    try:
        await run_migrations(async_engine)
    finally:
        await async_engine.dispose()

    engine = create_engine(f"sqlite:///{database_path.as_posix()}")
    try:
        with engine.connect() as connection:
            current = connection.execute(
                text(
                    """
                    SELECT channel_name, id
                    FROM gateway_sessions
                    WHERE is_current
                    ORDER BY channel_name
                    """
                )
            ).all()
    finally:
        engine.dispose()

    assert current == [
        ("voice", "00000000000000000000000000000003"),
        ("web", "00000000000000000000000000000002"),
    ]


def _downgrade(connection: Connection, revision: str) -> None:
    config = Config(_GATEWAY_ROOT / "alembic.ini")
    config.set_main_option("script_location", str(_GATEWAY_ROOT / "migrations"))
    config.attributes["connection"] = connection
    command.downgrade(config, revision)
