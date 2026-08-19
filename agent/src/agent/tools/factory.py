import agenttoolkit
from agenttoolkit import (
    CallLoggingMiddleware,
    ErrorBoundaryMiddleware,
    Skills,
    ToolContext,
)
from agenttoolkit.builtins import DockerSandbox, Workspace

from agent.tools.actions import register_tools
from agent.tools.handler import IpLocationClient, OpenMeteoClient, TavilySearchClient
from agent.tools.sandbox import SandboxConfig, create_tool_context


class AgentTools(agenttoolkit.Tools):
    """Agent tool catalog and the resources required to execute it."""

    def __init__(self, context: ToolContext) -> None:
        super().__init__(
            context=context,
            middleware=(CallLoggingMiddleware(), ErrorBoundaryMiddleware()),
        )
        self._sandbox = context.resolve(DockerSandbox)

    async def prepare(self) -> None:
        if self._sandbox is not None:
            await self._sandbox.open()

    async def aclose(self) -> None:
        if self._sandbox is not None:
            await self._sandbox.close()


def create_tools(context: ToolContext | None = None) -> AgentTools:
    selected_context = context if context is not None else create_tool_context()
    tools = AgentTools(selected_context)
    register_tools(tools)
    return tools


def build_tools(
    *dependencies: object,
    skills: Skills | None = None,
    workspace: Workspace | None = None,
    sandbox: SandboxConfig | None = None,
    additional_tools: agenttoolkit.Tools | None = None,
) -> AgentTools:
    tool_context = create_tool_context(
        *dependencies,
        IpLocationClient(),
        OpenMeteoClient(),
        TavilySearchClient(),
        skills,
        workspace=workspace,
        sandbox=sandbox,
    )
    tools = create_tools(tool_context)
    if additional_tools is not None:
        tools.merge(additional_tools)
    return tools
