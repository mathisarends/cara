from collections.abc import Sequence

import agenttoolkit
from agenttoolkit import (
    DependencyProvider,
    Skills,
    ToolContext,
)
from agenttoolkit.builtins import (
    CommandDefaults,
    CommandRunner,
    LocalShellRunner,
    LocalWorkspace,
    Workspace,
)
from agenttoolkit.dependency import DependencyContainer

from agent.clock import LocalClock
from agent.tools.actions import register_tools
from agent.tools.dependency_provider import BuiltinDependencies
from agent.tools.middleware import ToolResultMiddleware
from agent.workspace import resolve_workspace_root


class AgentTools(agenttoolkit.Tools):
    """The tools exposed to the agent model."""

    def __init__(
        self,
        context: ToolContext,
        *,
        container: DependencyContainer | None = None,
        dependencies: Sequence[DependencyProvider] | None = None,
    ) -> None:
        super().__init__(
            context=context,
            container=container,
            dependencies=dependencies,
            middleware=(ToolResultMiddleware(),),
        )


def build_tools(
    *,
    injected_dependencies: Sequence[object] = (),
    skills: Skills | None = None,
    workspace: Workspace | None = None,
    additional_tools: agenttoolkit.Tools | None = None,
    context: ToolContext | None = None,
    container: DependencyContainer | None = None,
) -> AgentTools:
    if context is not None and (
        injected_dependencies or skills is not None or workspace is not None
    ):
        raise ValueError(
            "A prebuilt context cannot be combined with context dependencies"
        )
    tool_context = (
        context
        if context is not None
        else _create_tool_context(
            *injected_dependencies,
            skills,
            workspace=workspace,
        )
    )
    tools = _create_tools(
        tool_context,
        container=container,
        dependencies=None if container is not None else (BuiltinDependencies(),),
    )
    if additional_tools is not None:
        tools.merge(additional_tools)
    return tools


def _create_tools(
    context: ToolContext | None = None,
    *,
    container: DependencyContainer | None = None,
    dependencies: Sequence[DependencyProvider] | None = None,
) -> AgentTools:
    selected_context = context if context is not None else _create_tool_context()
    tools = AgentTools(
        selected_context,
        container=container,
        dependencies=dependencies,
    )
    register_tools(tools)
    return tools


def _create_tool_context(
    *dependencies: object,
    workspace: Workspace | None = None,
    runner: CommandRunner | None = None,
    clock: LocalClock | None = None,
) -> ToolContext:
    selected_workspace = workspace or _default_workspace()
    selected_runner = runner or _default_runner(selected_workspace)
    return ToolContext(
        selected_workspace,
        selected_runner,
        clock or LocalClock(),
        *dependencies,
    )


def _default_workspace() -> LocalWorkspace:
    return LocalWorkspace(resolve_workspace_root())


def _default_runner(workspace: Workspace) -> CommandRunner:
    return LocalShellRunner(CommandDefaults(working_directory=workspace.root))
