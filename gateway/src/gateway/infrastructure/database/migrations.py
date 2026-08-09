from pathlib import Path

from alembic.command import upgrade
from alembic.config import Config

_MIGRATIONS_ROOT = Path(__file__).resolve().parents[4]


def run_migrations(url: str) -> None:
    config = Config(_MIGRATIONS_ROOT / "alembic.ini")
    config.set_main_option("script_location", str(_MIGRATIONS_ROOT / "migrations"))
    config.set_main_option("sqlalchemy.url", url)
    upgrade(config, "head")
