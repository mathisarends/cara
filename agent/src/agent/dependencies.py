from collections.abc import Callable, Sequence
from dataclasses import dataclass

from agenttoolkit import DependencyProvider, Skills, ToolContext, provide
from agenttoolkit.builtins import (
    CommandDefaults,
    CommandRunner,
    LocalShellRunner,
    LocalWorkspace,
    Workspace,
)

from agent.clock import LocalClock
from agent.configuration import AgentSettings
from agent.models import ModelSwitch
from agent.workspace import resolve_workspace_root
from llm import ChatModel, CodexModel, CodexReasoningEffort, create_codex_model

type _ModelFactories = dict[str, Callable[[str | None], ChatModel]]


@dataclass(frozen=True, slots=True)
class AgentComponents:
    workspace: Workspace
    skills: Skills | None
    models: ModelSwitch
    clock: LocalClock
    tool_context: ToolContext


class ConfiguredDependencies(DependencyProvider):
    def __init__(
        self,
        settings: AgentSettings,
        tool_dependencies: Sequence[object] = (),
        initial_model: ChatModel | None = None,
        workspace: Workspace | None = None,
        command_runner: CommandRunner | None = None,
    ) -> None:
        self._settings = settings
        self._tool_dependencies = tuple(tool_dependencies)
        self._initial_model = initial_model
        self._workspace = workspace
        self._command_runner = command_runner

    @provide
    def settings(self) -> AgentSettings:
        return self._settings

    @provide
    def workspace(self, settings: AgentSettings) -> Workspace:
        if self._workspace is not None:
            return self._workspace
        return LocalWorkspace(
            resolve_workspace_root(settings.workspace.root),
            max_file_bytes=settings.workspace.max_file_bytes,
        )

    @provide
    def skills(self, workspace: Workspace) -> Skills | None:
        skills_root = workspace.root / "skills"
        return Skills.from_dir(skills_root) if skills_root.is_dir() else None

    @provide
    def command_runner(
        self,
        settings: AgentSettings,
        workspace: Workspace,
    ) -> CommandRunner:
        if self._command_runner is not None:
            return self._command_runner
        return LocalShellRunner(CommandDefaults(working_directory=workspace.root))

    @provide
    def clock(self, settings: AgentSettings) -> LocalClock:
        return LocalClock(settings.timezone)

    @provide
    def model_factories(self, settings: AgentSettings) -> _ModelFactories:
        return {
            model.value: _codex_model_factory(model)
            for model in settings.models.available
        }

    @provide
    def model_switch(
        self,
        settings: AgentSettings,
        model_factories: _ModelFactories,
    ) -> ModelSwitch:
        return ModelSwitch.configurable(
            model_factories,
            default=settings.models.default.value,
            reasoning_efforts=tuple(effort.value for effort in CodexReasoningEffort),
            initial_model=self._initial_model,
        )

    @provide
    def tool_context(
        self,
        workspace: Workspace,
        command_runner: CommandRunner,
        skills: Skills | None,
        model_switch: ModelSwitch,
        clock: LocalClock,
    ) -> ToolContext:
        return ToolContext(
            workspace,
            command_runner,
            skills,
            model_switch,
            clock,
            *self._tool_dependencies,
        )

    @provide
    def agent_components(
        self,
        workspace: Workspace,
        skills: Skills | None,
        model_switch: ModelSwitch,
        clock: LocalClock,
        tool_context: ToolContext,
    ) -> AgentComponents:
        return AgentComponents(
            workspace=workspace,
            skills=skills,
            models=model_switch,
            clock=clock,
            tool_context=tool_context,
        )


def _codex_model_factory(
    configured_model: CodexModel,
) -> Callable[[str | None], ChatModel]:
    def create(reasoning_effort: str | None) -> ChatModel:
        if reasoning_effort is None:
            return create_codex_model(configured_model)
        return create_codex_model(
            configured_model,
            reasoning_effort=CodexReasoningEffort(reasoning_effort),
        )

    return create
