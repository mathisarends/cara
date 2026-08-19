import os
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

from agenttoolkit.builtins import (
    BindMount,
    CommandDefaults,
    CommandLimits,
    CommandRunner,
    DockerSandbox,
    SandboxLimits,
    SandboxPolicy,
)
from pydantic import BaseModel, ConfigDict

from agent.sandbox.config import SandboxDefinition, load_sandbox_definition


class SandboxConfig(BaseModel):
    """Application overrides for the configured sandbox."""

    model_config = ConfigDict(arbitrary_types_allowed=True, extra="forbid")

    runner: CommandRunner | None = None
    environment: Mapping[str, str] | None = None
    mounts: Sequence[BindMount] | None = None
    network_access: bool | None = None


def create_sandbox(
    working_directory: Path,
    *,
    definition: SandboxDefinition | None = None,
    environment: Mapping[str, str] | None = None,
    mounts: Sequence[BindMount] = (),
    network_access: bool | None = None,
) -> DockerSandbox:
    selected_definition = definition or load_sandbox_definition()
    _validate_mounts(selected_definition, mounts)
    configured_mounts = _cli_credential_mounts(selected_definition)
    defaults = selected_definition.defaults
    limits = selected_definition.limits
    return DockerSandbox(
        selected_definition.image,
        defaults=CommandDefaults(
            working_directory=working_directory,
            environment={
                "HOME": str(defaults.home),
                **(environment or {}),
            },
            limits=CommandLimits(
                timeout_seconds=defaults.timeout_seconds,
                max_output_bytes=defaults.max_output_bytes,
            ),
        ),
        policy=SandboxPolicy.for_workspace(
            working_directory,
            enable_network_access=(
                selected_definition.network_access
                if network_access is None
                else network_access
            ),
            limits=SandboxLimits(
                memory_bytes=limits.memory_bytes,
                pids=limits.pids,
                cpus=limits.cpus,
            ),
        ),
        mounts=(*configured_mounts, *mounts),
        shell=str(selected_definition.shell),
    )


def _validate_mounts(
    definition: SandboxDefinition, mounts: Sequence[BindMount]
) -> None:
    reserved_targets = definition.reserved_targets
    if any(mount.target in reserved_targets for mount in mounts):
        targets = ", ".join(map(str, sorted(reserved_targets)))
        raise ValueError(
            f"Sandbox mount target is reserved; reserved targets: {targets}."
        )


def _cli_credential_mounts(
    definition: SandboxDefinition,
) -> tuple[BindMount, ...]:
    return tuple(
        BindMount.read_write(host_dir, mount.target)
        for mount in definition.mounts.cli_credentials
        if (host_dir := _host_config_dir(mount.name)) is not None and host_dir.is_dir()
    )


def _host_config_dir(name: str) -> Path | None:
    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA")
        return Path(appdata) / name if appdata else None
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / name
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / name
