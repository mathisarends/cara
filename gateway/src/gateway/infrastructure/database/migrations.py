import logging
from pathlib import Path

from alembic.command import upgrade
from alembic.config import Config

from gateway.infrastructure.database.settings import DatabaseSettings

_MIGRATIONS_ROOT = Path(__file__).resolve().parents[4]

logger = logging.getLogger(__name__)


def run_migrations(url: str) -> None:
    upgrade(_config(url), "head")


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    url = DatabaseSettings().async_url
    logger.info("Migrating database to head")
    run_migrations(url)
    logger.info("Database is up to date")


def _config(url: str) -> Config:
    config = Config(_MIGRATIONS_ROOT / "alembic.ini")
    config.set_main_option("script_location", str(_MIGRATIONS_ROOT / "migrations"))
    config.set_main_option("sqlalchemy.url", url)
    return config


if __name__ == "__main__":
    main()
