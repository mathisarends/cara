from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class GatewaySettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="GATEWAY_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    scheduler_database_path: Path = Path("temp/scheduled-jobs.sqlite3")
    scheduler_timezone: str = "UTC"
