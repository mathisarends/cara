from collections.abc import Mapping, Sequence
from pathlib import Path
from types import TracebackType
from typing import Self

import agenttoolkit
from agenttoolkit import (
    CallLoggingMiddleware,
    ErrorBoundaryMiddleware,
    Skills,
    ToolContext,
)
from agenttoolkit.builtins import BindMount, DockerSandbox, Workspace
from config import CaraConfig

from agent.tools.actions import register_tools
from agent.tools.handler import IpLocationClient, OpenMeteoClient, TavilySearchClient
from agent.tools.sandbox import create_tool_context


def create_tools(context: ToolContext | None = None) -> "_ManagedTools":
    selected_context = context if context is not None else create_tool_context()
    tools = _new_tools(selected_context)
    register_tools(tools)
    return tools


def build_tools(
    *dependencies: object,
    configuration: CaraConfig | None = None,
    skills: Skills | None = None,
    workspace: Workspace | None = None,
    workspace_root: Path | None = None,
    sandbox_environment: Mapping[str, str] | None = None,
    sandbox_mounts: Sequence[BindMount] | None = None,
    sandbox_network_access: bool | None = None,
    tools: agenttoolkit.Tools | None = None,
) -> "_ManagedTools":
    configured_dependencies = [
        *dependencies,
        IpLocationClient(),
        OpenMeteoClient(),
        TavilySearchClient(),
    ]
    if skills is not None:
        configured_dependencies.append(skills)
    tool_context = create_tool_context(
        *configured_dependencies,
        configuration=configuration,
        workspace=workspace,
        workspace_root=workspace_root,
        sandbox_environment=sandbox_environment,
        sandbox_mounts=sandbox_mounts,
        sandbox_network_access=sandbox_network_access,
    )
    if tools is None:
        return create_tools(tool_context)
    configured_tools = _new_tools(tool_context)
    configured_tools.merge(tools)
    return configured_tools


class _ManagedTools(agenttoolkit.Tools):
    def __init__(self, context: ToolContext) -> None:
        super().__init__(
            context=context,
            middleware=(CallLoggingMiddleware(), ErrorBoundaryMiddleware()),
        )
        self._sandbox = context.resolve(DockerSandbox)

    async def __aenter__(self) -> Self:
        if self._sandbox is not None:
            await self._sandbox.open()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if self._sandbox is not None:
            await self._sandbox.close()


def _new_tools(context: ToolContext) -> _ManagedTools:
    return _ManagedTools(context)
