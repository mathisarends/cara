from pathlib import Path
from typing import Annotated

from pydantic import AfterValidator, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _expand_user(path: Path) -> Path:
    return path.expanduser()


type _ExpandedPath = Annotated[Path, AfterValidator(_expand_user)]


def _default_state_root() -> Path:
    return Path.home() / ".cara"


def _default_workspace_root() -> Path:
    return _default_state_root() / "workspace"


class CaraPaths(BaseSettings):
    """Persistent Cara paths loaded from environment variables or `.env`."""

    model_config = SettingsConfigDict(
        env_prefix="CARA_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    state_root: _ExpandedPath = Field(default_factory=_default_state_root)
    workspace_root: _ExpandedPath = Field(default_factory=_default_workspace_root)
