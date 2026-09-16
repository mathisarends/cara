from collections.abc import Callable, Sequence

from agenttoolkit import DependencyProvider, Tools
from agenttoolkit.builtins import CommandRunner, Workspace
from agenttoolkit.dependency import DependencyContainer

from agent.agent import Agent
from agent.configuration import AgentSettings
from agent.dependencies import AgentComponents, ConfiguredDependencies
from agent.tools import ToolRegistrar, build_tools
from llm import ChatModel, Message


class AgentFactory:
    """Build a fully configured agent without depending on a transport plugin."""

    def __init__(
        self,
        settings: AgentSettings,
        *,
        model_factory: Callable[[], ChatModel],
        workspace: Workspace,
        command_runner: CommandRunner,
        additional_tools: Tools | None = None,
        tool_registrars: Sequence[ToolRegistrar] = (),
        tool_dependency_providers: Sequence[DependencyProvider] = (),
    ) -> None:
        self._settings = settings
        self._model_factory = model_factory
        self._workspace = workspace
        self._command_runner = command_runner
        self._additional_tools = additional_tools
        self._tool_registrars = tuple(tool_registrars)
        self._tool_dependency_providers = tuple(tool_dependency_providers)

    async def create(
        self,
        messages: Sequence[Message] = (),
        *,
        tool_dependencies: Sequence[object] = (),
    ) -> Agent:
        model = self._model_factory()
        container = DependencyContainer(
            ConfiguredDependencies(
                self._settings,
                model,
                tool_dependencies=tool_dependencies,
                workspace=self._workspace,
                command_runner=self._command_runner,
            ),
            *self._tool_dependency_providers,
        )
        components = await container.get(AgentComponents)
        tools = build_tools(
            context=components.tool_context,
            container=container,
            additional_tools=self._additional_tools,
            registrars=self._tool_registrars,
        )
        return Agent(
            model=components.model,
            tools=tools,
            skills=components.skills,
            clock=components.clock,
            system_prompt=self._settings.system_prompt,
            workspace_root=components.workspace.root,
            messages=messages,
        )
