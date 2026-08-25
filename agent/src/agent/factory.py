from collections.abc import Sequence
from typing import cast

from agenttoolkit import Skills, ToolContext
from agenttoolkit.builtins import Workspace
from agenttoolkit.dependency import DependencyContainer
from llmify import Message

from agent.agent import Agent
from agent.configuration import AgentSettings
from agent.dependencies import ConfiguredDependencies
from agent.models import ModelSwitch
from agent.tools import build_tools
from agent.tools.dependency_provider import BuiltinDependencies

_SKILLS_DEPENDENCY = cast(type[Skills | None], Skills | None)


class AgentFactory:
    """Build a fully configured agent without depending on a transport plugin."""

    def __init__(self, settings: AgentSettings) -> None:
        self._settings = settings

    async def create(self, messages: Sequence[Message] = ()) -> Agent:
        container = DependencyContainer(
            ConfiguredDependencies(self._settings),
            BuiltinDependencies(),
        )
        settings = await container.get(AgentSettings)
        workspace = await container.get(Workspace)
        skills = await container.get(_SKILLS_DEPENDENCY)
        models = await container.get(ModelSwitch)
        tool_context = await container.get(ToolContext)
        tools = build_tools(
            context=tool_context,
            container=container,
        )
        return Agent(
            models=models,
            tools=tools,
            skills=skills,
            system_prompt=settings.system_prompt,
            workspace_root=workspace.root,
            messages=messages,
        )
