import os
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path, PurePosixPath

from agenttoolkit import ToolContext
from agenttoolkit.builtins import (
    BindMount,
    CommandDefaults,
    CommandLimits,
    CommandRunner,
    DockerSandbox,
    LocalWorkspace,
    SandboxLimits,
    SandboxPolicy,
    Workspace,
)
from pydantic import BaseModel, ConfigDict

_BASH_IMAGE = "cara-bash-sandbox:latest"


class SandboxConfig(BaseModel):
    """Sandbox-scoped configuration for `create_tool_context`."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    runner: CommandRunner | None = None
    environment: Mapping[str, str] | None = None
    mounts: Sequence[BindMount] | None = None
    network_access: bool | None = None


def create_tool_context(
    *dependencies: object,
    workspace: Workspace | None = None,
    sandbox: SandboxConfig | None = None,
) -> ToolContext:
    sandbox = sandbox or SandboxConfig()
    if sandbox.runner is not None and (
        sandbox.environment or sandbox.mounts or sandbox.network_access is not None
    ):
        raise ValueError(
            "Configure environment, mounts, and network access on the "
            "provided sandbox runner directly."
        )
    selected_workspace = workspace or _default_workspace()
    selected_mounts = tuple(sandbox.mounts or ())
    selected_network_access = bool(sandbox.network_access)
    selected_sandbox = sandbox.runner or _default_sandbox(
        selected_workspace.root,
        environment=sandbox.environment,
        mounts=selected_mounts,
        network_access=selected_network_access,
    )
    return ToolContext(selected_workspace, selected_sandbox, *dependencies)


def _default_workspace() -> LocalWorkspace:
    return LocalWorkspace(Path.cwd(), max_file_bytes=None)


def _default_sandbox(
    working_directory: Path,
    *,
    environment: Mapping[str, str] | None = None,
    mounts: Sequence[BindMount] = (),
    network_access: bool = False,
) -> DockerSandbox:
    if any(mount.target == PurePosixPath("/workspace") for mount in mounts):
        raise ValueError("'/workspace' is reserved for Cara's primary workspace.")
    return DockerSandbox(
        _BASH_IMAGE,
        defaults=CommandDefaults(
            working_directory=working_directory,
            environment={"HOME": "/tmp", **(environment or {})},
            limits=CommandLimits(timeout_seconds=15, max_output_bytes=1_000_000),
        ),
        policy=SandboxPolicy.for_workspace(
            working_directory,
            enable_network_access=network_access,
            limits=SandboxLimits(
                memory_bytes=256 * 1024 * 1024,
                pids=64,
                cpus=1,
            ),
        ),
        mounts=(*_cli_credential_mounts(), *mounts),
        shell="/bin/bash",
    )


_CLI_CREDENTIAL_TOOLS = ("huego", "spoti", "withings-client")


def _cli_credential_mounts() -> tuple[BindMount, ...]:
    # Sandbox HOME is /tmp, so the tools' UserConfigDir resolves under /tmp/.config.
    return tuple(
        BindMount.read_write(host_dir, f"/tmp/.config/{name}")
        for name in _CLI_CREDENTIAL_TOOLS
        if (host_dir := _host_config_dir(name)) is not None and host_dir.is_dir()
    )


def _host_config_dir(name: str) -> Path | None:
    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA")
        return Path(appdata) / name if appdata else None
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / name
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / name
