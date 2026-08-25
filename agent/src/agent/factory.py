from collections.abc import Sequence

from agenttoolkit.dependency import DependencyContainer
from llmify import Message

from agent.agent import Agent
from agent.configuration import AgentSettings
from agent.dependencies import AgentComponents, ConfiguredDependencies
from agent.tools import build_tools
from agent.tools.dependency_provider import BuiltinDependencies


class AgentFactory:
    """Build a fully configured agent without depending on a transport plugin."""

    def __init__(self, settings: AgentSettings) -> None:
        self._settings = settings

    async def create(
        self,
        messages: Sequence[Message] = (),
        *,
        tool_dependencies: Sequence[object] = (),
    ) -> Agent:
        container = DependencyContainer(
            ConfiguredDependencies(
                self._settings,
                tool_dependencies=tool_dependencies,
            ),
            BuiltinDependencies(),
        )
        components = await container.get(AgentComponents)
        tools = build_tools(
            context=components.tool_context,
            container=container,
        )
        return Agent(
            models=components.models,
            tools=tools,
            skills=components.skills,
            system_prompt=self._settings.system_prompt,
            workspace_root=components.workspace.root,
            messages=messages,
        )
