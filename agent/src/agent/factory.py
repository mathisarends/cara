from collections.abc import Sequence

from agenttoolkit import Tools
from agenttoolkit.builtins import CommandRunner, Workspace
from agenttoolkit.dependency import DependencyContainer

from agent.agent import Agent
from agent.configuration import AgentSettings
from agent.dependencies import AgentComponents, ConfiguredDependencies
from agent.tools import build_tools
from agent.tools.dependency_provider import BuiltinDependencies
from llm import ChatModel, Message, create_codex_model


class AgentFactory:
    """Build a fully configured agent without depending on a transport plugin."""

    def __init__(
        self,
        settings: AgentSettings,
        *,
        workspace: Workspace,
        command_runner: CommandRunner,
        additional_tools: Tools | None = None,
    ) -> None:
        self._settings = settings
        self._workspace = workspace
        self._command_runner = command_runner
        self._additional_tools = additional_tools

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
                workspace=self._workspace,
                command_runner=self._command_runner,
            ),
            BuiltinDependencies(),
        )
        components = await container.get(AgentComponents)
        tools = build_tools(
            context=components.tool_context,
            container=container,
            additional_tools=self._additional_tools,
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

    async def prewarm_model(self) -> ChatModel:
        return create_codex_model(self._settings.models.default)
