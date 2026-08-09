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
from config import CaraPaths

_BASH_IMAGE = "cara-bash-sandbox:latest"


def create_tool_context(
    *dependencies: object,
    workspace: Workspace | None = None,
    workspace_root: Path | None = None,
    sandbox: CommandRunner | None = None,
    sandbox_environment: Mapping[str, str] | None = None,
    sandbox_mounts: Sequence[BindMount] = (),
    sandbox_network_access: bool = False,
) -> ToolContext:
    if workspace is not None and workspace_root is not None:
        raise ValueError("Provide either workspace or workspace_root, not both.")
    if sandbox is not None and (
        sandbox_environment or sandbox_mounts or sandbox_network_access
    ):
        raise ValueError(
            "Configure environment, mounts, and network access on the "
            "provided sandbox directly."
        )
    selected_workspace = workspace or _default_workspace(workspace_root)
    selected_sandbox = sandbox or _default_sandbox(
        selected_workspace.root,
        environment=sandbox_environment,
        mounts=sandbox_mounts,
        network_access=sandbox_network_access,
    )
    return ToolContext(selected_workspace, selected_sandbox, *dependencies)


def _default_workspace(root: Path | None = None) -> LocalWorkspace:
    selected_root = root if root is not None else CaraPaths().workspace_root
    return LocalWorkspace(selected_root, max_file_bytes=1_000_000)


def _default_sandbox(
    working_directory: Path,
    *,
    environment: Mapping[str, str] | None = None,
    mounts: Sequence[BindMount] = (),
    network_access: bool = False,
) -> DockerSandbox:
    workspace_target = PurePosixPath("/workspace")
    if any(
        mount.target == workspace_target or workspace_target in mount.target.parents
        for mount in mounts
    ):
        raise ValueError("'/workspace' and its children are reserved for Cara.")
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
