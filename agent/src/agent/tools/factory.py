from collections.abc import Sequence
from pathlib import Path

import agenttoolkit
from agenttoolkit import (
    Skills,
    ToolContext,
)
from agenttoolkit.builtins import (
    CommandDefaults,
    CommandRunner,
    DockerSandbox,
    LocalShellRunner,
    LocalWorkspace,
    Workspace,
)

from agent.sandbox import SandboxDefinition, create_sandbox
from agent.tools.actions import register_tools
from agent.tools.handler import IpLocationLookup, OpenMeteoWeather, TavilyWebSearch
from agent.tools.middleware import ToolResultMiddleware


class AgentTools(agenttoolkit.Tools):
    """Agent tool catalog and the resources required to execute it."""

    def __init__(self, context: ToolContext) -> None:
        super().__init__(
            context=context,
            middleware=(ToolResultMiddleware(),),
        )
        self._sandbox = context.resolve(DockerSandbox)

    async def prepare(self) -> None:
        if self._sandbox is not None:
            await self._sandbox.open()

    async def aclose(self) -> None:
        if self._sandbox is not None:
            await self._sandbox.close()


def build_tools(
    *,
    injected_dependencies: Sequence[object] = (),
    skills: Skills | None = None,
    workspace: Workspace | None = None,
    sandbox: SandboxDefinition | None = None,
    additional_tools: agenttoolkit.Tools | None = None,
) -> AgentTools:
    dependencies = (*_builtin_handlers(), *injected_dependencies, skills)
    tool_context = _create_tool_context(
        *dependencies,
        workspace=workspace,
        sandbox=sandbox,
    )
    tools = _create_tools(tool_context)
    if additional_tools is not None:
        tools.merge(additional_tools)
    return tools


def _create_tools(context: ToolContext | None = None) -> AgentTools:
    selected_context = context if context is not None else _create_tool_context()
    tools = AgentTools(selected_context)
    register_tools(tools)
    return tools


def _create_tool_context(
    *dependencies: object,
    workspace: Workspace | None = None,
    sandbox: SandboxDefinition | None = None,
    runner: CommandRunner | None = None,
) -> ToolContext:
    selected_workspace = workspace or _default_workspace(sandbox)
    selected_runner = runner or _default_runner(sandbox, selected_workspace)
    return ToolContext(selected_workspace, selected_runner, *dependencies)


def _builtin_handlers() -> tuple[object, ...]:
    return (IpLocationLookup(), OpenMeteoWeather(), TavilyWebSearch())


def _default_workspace(sandbox: SandboxDefinition | None) -> LocalWorkspace:
    if sandbox is None:
        return LocalWorkspace(Path.cwd())
    return LocalWorkspace(
        sandbox.resolve_workspace_root(),
        max_file_bytes=sandbox.workspace.max_file_bytes,
    )


def _default_runner(
    sandbox: SandboxDefinition | None, workspace: Workspace
) -> CommandRunner:
    if sandbox is None:
        return LocalShellRunner(CommandDefaults(working_directory=workspace.root))
    return create_sandbox(workspace.root, sandbox)
