import asyncio
import logging
from pathlib import Path

from alembic.command import upgrade
from alembic.config import Config
from sqlalchemy import Connection
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from gateway.platform.database.settings import DatabaseSettings

_MIGRATIONS_ROOT = Path(__file__).resolve().parents[4]

logger = logging.getLogger(__name__)


async def run_migrations(engine: AsyncEngine) -> None:
    config = _config()
    async with engine.connect() as connection:
        await connection.run_sync(_upgrade, config)


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    asyncio.run(_run())


async def _run() -> None:
    settings = DatabaseSettings()
    engine = create_async_engine(settings.async_url)
    try:
        logger.info("Migrating database to head")
        await run_migrations(engine)
        logger.info("Database is up to date")
    finally:
        await engine.dispose()


def _upgrade(connection: Connection, config: Config) -> None:
    config.attributes["connection"] = connection
    upgrade(config, "head")


def _config() -> Config:
    config = Config(_MIGRATIONS_ROOT / "alembic.ini")
    config.set_main_option("script_location", str(_MIGRATIONS_ROOT / "migrations"))
    return config


if __name__ == "__main__":
    main()
