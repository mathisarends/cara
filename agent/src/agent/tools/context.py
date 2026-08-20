from agenttoolkit import ToolContext
from agenttoolkit.builtins import LocalWorkspace, Workspace

from agent.sandbox import (
    SandboxConfig,
    SandboxDefinition,
    create_sandbox,
    load_sandbox_definition,
)


def create_tool_context(
    *dependencies: object,
    workspace: Workspace | None = None,
    sandbox: SandboxConfig | None = None,
    definition: SandboxDefinition | None = None,
) -> ToolContext:
    overrides = sandbox or SandboxConfig()
    if overrides.runner is not None and (overrides.environment or overrides.mounts):
        raise ValueError(
            "Configure environment and mounts on the provided sandbox runner directly."
        )
    selected_definition = definition or load_sandbox_definition()
    selected_workspace = workspace or _default_workspace(selected_definition)
    selected_sandbox = overrides.runner or create_sandbox(
        selected_workspace.root,
        definition=selected_definition,
        environment=overrides.environment,
        mounts=overrides.mounts or (),
    )
    return ToolContext(selected_workspace, selected_sandbox, *dependencies)


def _default_workspace(definition: SandboxDefinition) -> LocalWorkspace:
    return LocalWorkspace(
        definition.resolve_workspace_root(),
        max_file_bytes=definition.workspace.max_file_bytes,
    )
