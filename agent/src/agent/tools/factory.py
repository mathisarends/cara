from collections.abc import Callable, Sequence

import agenttoolkit
from agenttoolkit import (
    DependencyProvider,
    ToolContext,
)
from agenttoolkit.dependency import DependencyContainer

from agent.tools.middleware import ToolResultMiddleware

type ToolRegistrar = Callable[[agenttoolkit.Tools], None]


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
    registrars: Sequence[ToolRegistrar] = (),
) -> AgentTools:
    tools = _create_tools(
        context,
        container=container,
        dependencies=() if container is None else None,
    )
    for register in registrars:
        register(tools)
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
    return tools
