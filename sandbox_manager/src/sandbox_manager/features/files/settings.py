from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class FilesSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="CARA_SANDBOX_",
        extra="ignore",
    )

    workspace_root: Path = Path("/workspace")
