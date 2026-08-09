from pathlib import Path, PurePosixPath
from typing import Annotated, Self

import json5
from pydantic import AfterValidator, BaseModel, ConfigDict, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _expand_user(path: Path) -> Path:
    return path.expanduser()


type _ExpandedPath = Annotated[Path, AfterValidator(_expand_user)]


def _default_state_root() -> Path:
    return Path.home() / ".cara"


def _default_workspace_root() -> Path:
    return _default_state_root() / "workspace"


def _parse_bind_spec(spec: str) -> dict[str, object]:
    try:
        source, target, mode = spec.rsplit(":", maxsplit=2)
    except ValueError as error:
        raise ValueError(
            "Docker binds must use 'source:target:ro' or 'source:target:rw'."
        ) from error
    if not source or not target or mode not in {"ro", "rw"}:
        raise ValueError(
            "Docker binds must use 'source:target:ro' or 'source:target:rw'."
        )
    return {"source": source, "target": target, "writable": mode == "rw"}


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

    @property
    def config_file(self) -> Path:
        return self.state_root / "cara.json"


class DockerBind(BaseModel):
    """A validated host-to-container Docker bind mount."""

    model_config = ConfigDict(frozen=True)

    source: _ExpandedPath
    target: PurePosixPath
    writable: bool = False

    @model_validator(mode="before")
    @classmethod
    def parse_string_spec(cls, value: object) -> object:
        if isinstance(value, str):
            return _parse_bind_spec(value)
        return value

    @model_validator(mode="after")
    def validate_target(self) -> Self:
        if (
            not self.target.is_absolute()
            or self.target == PurePosixPath("/")
            or ".." in self.target.parts
        ):
            raise ValueError(
                "Docker bind targets must be absolute container paths below '/'."
            )
        return self


class CaraConfig(BaseModel):
    """Runtime paths and mounts resolved from Cara's external configuration."""

    model_config = ConfigDict(frozen=True)

    workspace_root: _ExpandedPath
    docker_binds: tuple[DockerBind, ...] = ()
    sandbox_network_access: bool = False


class _DockerConfig(BaseModel):
    binds: tuple[DockerBind, ...] = ()


class _SandboxConfig(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    network_access: bool = Field(default=False, alias="networkAccess")
    docker: _DockerConfig = Field(default_factory=_DockerConfig)


class _AgentDefaults(BaseModel):
    workspace: _ExpandedPath | None = None
    sandbox: _SandboxConfig = Field(default_factory=_SandboxConfig)


class _AgentsConfig(BaseModel):
    defaults: _AgentDefaults = Field(default_factory=_AgentDefaults)


class _ConfigFile(BaseModel):
    agents: _AgentsConfig = Field(default_factory=_AgentsConfig)


def load_cara_config(paths: CaraPaths | None = None) -> CaraConfig:
    """Load `cara.json`, falling back to defaults when the file is absent."""

    selected_paths = paths or CaraPaths()
    if selected_paths.config_file.is_file():
        raw_config = json5.loads(selected_paths.config_file.read_text(encoding="utf-8"))
        file_config = _ConfigFile.model_validate(raw_config)
    else:
        file_config = _ConfigFile()

    defaults = file_config.agents.defaults
    workspace_root = defaults.workspace or selected_paths.workspace_root
    if "workspace_root" in selected_paths.model_fields_set:
        workspace_root = selected_paths.workspace_root
    return CaraConfig(
        workspace_root=workspace_root,
        docker_binds=defaults.sandbox.docker.binds,
        sandbox_network_access=defaults.sandbox.network_access,
    )
