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

_BASH_IMAGE = "cara-bash-sandbox:latest"


def create_tool_context(
    *dependencies: object,
    workspace: Workspace | None = None,
    sandbox: CommandRunner | None = None,
    sandbox_environment: Mapping[str, str] | None = None,
    sandbox_mounts: Sequence[BindMount] | None = None,
    sandbox_network_access: bool | None = None,
) -> ToolContext:
    if sandbox is not None and (
        sandbox_environment or sandbox_mounts or sandbox_network_access is not None
    ):
        raise ValueError(
            "Configure environment, mounts, and network access on the "
            "provided sandbox directly."
        )
    selected_workspace = workspace or _default_workspace()
    selected_mounts = tuple(sandbox_mounts or ())
    selected_network_access = bool(sandbox_network_access)
    selected_sandbox = sandbox or _default_sandbox(
        selected_workspace.root,
        environment=sandbox_environment,
        mounts=selected_mounts,
        network_access=selected_network_access,
    )
    return ToolContext(selected_workspace, selected_sandbox, *dependencies)


def _default_workspace() -> LocalWorkspace:
    return LocalWorkspace(Path(Path.cwd().anchor), max_file_bytes=None)


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
        mounts=mounts,
        shell="/bin/bash",
    )
