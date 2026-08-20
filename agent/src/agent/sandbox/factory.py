import os
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

from agenttoolkit.builtins import (
    BindMount,
    CommandDefaults,
    CommandLimits,
    SandboxLimits,
    SandboxPolicy,
)

from agent.sandbox.config import SandboxDefinition
from agent.sandbox.managed import ManagedSandbox


def create_sandbox(
    working_directory: Path,
    definition: SandboxDefinition,
    *,
    environment: Mapping[str, str] | None = None,
    mounts: Sequence[BindMount] = (),
) -> ManagedSandbox:
    _validate_mounts(definition, mounts)
    configured_mounts = _configured_mounts(definition)
    defaults = definition.defaults
    limits = definition.limits
    return ManagedSandbox(
        definition.image,
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
            enable_network_access=definition.network_access,
            limits=SandboxLimits(
                memory_bytes=limits.memory_bytes,
                pids=limits.pids,
                cpus=limits.cpus,
            ),
        ),
        mounts=(*configured_mounts, *mounts),
        shell=str(definition.shell),
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


def _configured_mounts(definition: SandboxDefinition) -> tuple[BindMount, ...]:
    return (*_path_mounts(definition), *_cli_credential_mounts(definition))


def _path_mounts(definition: SandboxDefinition) -> tuple[BindMount, ...]:
    mounts = []
    for mount in definition.mounts.paths:
        source = definition.resolve_path(mount.source)
        if not source.exists():
            raise ValueError(f"Sandbox mount source does not exist: {source}.")
        mounts.append(BindMount(source, mount.target, writable=mount.writable))
    return tuple(mounts)


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
