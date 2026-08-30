from collections.abc import Sequence

from agenttoolkit.dependency import DependencyContainer
from llmify import ChatCodex, ChatModel, Message

from agent.agent import Agent
from agent.configuration import AgentSettings
from agent.dependencies import AgentComponents, ConfiguredDependencies
from agent.tools import build_tools
from agent.tools.dependency_provider import BuiltinDependencies
from llm import create_codex_model


class AgentFactory:
    """Build a fully configured agent without depending on a transport plugin."""

    def __init__(self, settings: AgentSettings) -> None:
        self._settings = settings

    async def create(
        self,
        messages: Sequence[Message] = (),
        *,
        tool_dependencies: Sequence[object] = (),
        initial_model: ChatModel | None = None,
    ) -> Agent:
        container = DependencyContainer(
            ConfiguredDependencies(
                self._settings,
                tool_dependencies=tool_dependencies,
                initial_model=initial_model,
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
            clock=components.clock,
            system_prompt=self._settings.system_prompt,
            workspace_root=components.workspace.root,
            messages=messages,
        )

    async def prewarm_model(self) -> ChatCodex:
        model = create_codex_model(self._settings.models[0])
        await model.prewarm()
        return model
