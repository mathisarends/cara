from collections.abc import Sequence
from dataclasses import dataclass

from agenttoolkit import DependencyProvider, Skills, ToolContext, provide
from agenttoolkit.builtins import CommandRunner, Workspace

from agent.clock import LocalClock
from agent.configuration import AgentSettings
from llm import ChatModel


@dataclass(frozen=True, slots=True)
class AgentComponents:
    workspace: Workspace
    skills: Skills | None
    model: ChatModel
    clock: LocalClock
    tool_context: ToolContext


class ConfiguredDependencies(DependencyProvider):
    def __init__(
        self,
        settings: AgentSettings,
        model: ChatModel,
        workspace: Workspace,
        command_runner: CommandRunner,
        tool_dependencies: Sequence[object] = (),
    ) -> None:
        self._settings = settings
        self._model = model
        self._workspace = workspace
        self._command_runner = command_runner
        self._tool_dependencies = tuple(tool_dependencies)

    @provide
    def settings(self) -> AgentSettings:
        return self._settings

    @provide
    def workspace(self) -> Workspace:
        return self._workspace

    @provide
    def skills(self, workspace: Workspace) -> Skills | None:
        skills_root = workspace.root / "skills"
        return Skills.from_dir(skills_root) if skills_root.is_dir() else None

    @provide
    def command_runner(self) -> CommandRunner:
        return self._command_runner

    @provide
    def clock(self, settings: AgentSettings) -> LocalClock:
        return LocalClock(settings.timezone)

    @provide
    def model(self) -> ChatModel:
        return self._model

    @provide
    def tool_context(
        self,
        workspace: Workspace,
        command_runner: CommandRunner,
        skills: Skills | None,
        model: ChatModel,
        clock: LocalClock,
    ) -> ToolContext:
        return ToolContext(
            workspace,
            command_runner,
            skills,
            model,
            clock,
            *self._tool_dependencies,
        )

    @provide
    def agent_components(
        self,
        workspace: Workspace,
        skills: Skills | None,
        model: ChatModel,
        clock: LocalClock,
        tool_context: ToolContext,
    ) -> AgentComponents:
        return AgentComponents(
            workspace=workspace,
            skills=skills,
            model=model,
            clock=clock,
            tool_context=tool_context,
        )
