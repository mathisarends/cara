from collections.abc import Sequence

import agenttoolkit
from agenttoolkit import (
    DependencyProvider,
    ToolContext,
)
from agenttoolkit.dependency import DependencyContainer

from agent.tools.actions import register_tools
from agent.tools.dependency_provider import BuiltinDependencies
from agent.tools.middleware import ToolResultMiddleware


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
    context: ToolContext,
    additional_tools: agenttoolkit.Tools | None = None,
    container: DependencyContainer | None = None,
) -> AgentTools:
    tools = _create_tools(
        context,
        container=container,
        dependencies=None if container is not None else (BuiltinDependencies(),),
    )
    if additional_tools is not None:
        tools.merge(additional_tools)
    return tools


def _create_tools(
    context: ToolContext,
    *,
    container: DependencyContainer | None = None,
    dependencies: Sequence[DependencyProvider] | None = None,
) -> AgentTools:
    tools = AgentTools(
        context,
        container=container,
        dependencies=dependencies,
    )
    register_tools(tools)
    return tools
