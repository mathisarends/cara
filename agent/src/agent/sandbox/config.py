from pathlib import Path, PurePosixPath
from typing import Self

import yaml
from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, model_validator

from agent.workspace import resolve_workspace_root


class _ConfigModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SandboxDefaults(_ConfigModel):
    home: PurePosixPath
    timeout_seconds: float = Field(gt=0)
    max_output_bytes: int = Field(gt=0)


class SandboxResourceLimits(_ConfigModel):
    memory_bytes: int = Field(gt=0)
    pids: int = Field(gt=0)
    cpus: float = Field(gt=0)


class SandboxWorkspace(_ConfigModel):
    root: Path = Path(".")
    max_file_bytes: int | None = Field(default=None, gt=0)


class PathMount(_ConfigModel):
    source: Path
    target: PurePosixPath
    writable: bool = False


class CliCredentialMount(_ConfigModel):
    name: str = Field(min_length=1)
    target: PurePosixPath


class SandboxMounts(_ConfigModel):
    paths: tuple[PathMount, ...] = ()
    cli_credentials: tuple[CliCredentialMount, ...] = ()


class SandboxDefinition(_ConfigModel):
    image: str = Field(min_length=1)
    shell: PurePosixPath
    workspace: SandboxWorkspace = Field(default_factory=SandboxWorkspace)
    defaults: SandboxDefaults
    limits: SandboxResourceLimits
    network_access: bool = False
    mounts: SandboxMounts = Field(default_factory=SandboxMounts)
    reserved_targets: frozenset[PurePosixPath] = Field(default_factory=frozenset)

    _root: Path = PrivateAttr(default_factory=Path.cwd)

    def resolve_workspace_root(self) -> Path:
        return resolve_workspace_root(self.workspace.root, relative_to=self._root)

    def resolve_path(self, path: Path) -> Path:
        expanded = path.expanduser()
        if expanded.is_absolute():
            return expanded
        return self._root / expanded

    @model_validator(mode="after")
    def _reject_reserved_mount_targets(self) -> Self:
        configured_targets = {
            mount.target for mount in (*self.mounts.paths, *self.mounts.cli_credentials)
        }
        conflicts = configured_targets & self.reserved_targets
        if conflicts:
            targets = ", ".join(map(str, sorted(conflicts)))
            raise ValueError(f"Configured mount targets are reserved: {targets}.")
        return self

    @classmethod
    def from_yaml(cls, path: Path) -> Self:
        resolved_path = path.resolve()
        with resolved_path.open(encoding="utf-8") as config_file:
            raw_config = yaml.safe_load(config_file)
        definition = cls.model_validate(raw_config)
        definition._root = resolved_path.parent
        return definition
