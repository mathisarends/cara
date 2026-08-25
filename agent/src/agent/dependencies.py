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
from llmify import ChatModel

from agent.configuration import AgentSettings
from agent.models import ModelSwitch
from agent.sandbox import create_sandbox
from agent.workspace import resolve_workspace_root
from llm import CodexModel, CodexReasoningEffort, create_codex_model

type _ModelFactories = dict[str, Callable[[str | None], ChatModel]]


@dataclass(frozen=True, slots=True)
class AgentComponents:
    workspace: Workspace
    skills: Skills | None
    models: ModelSwitch
    tool_context: ToolContext


class ConfiguredDependencies(DependencyProvider):
    def __init__(
        self,
        settings: AgentSettings,
        tool_dependencies: Sequence[object] = (),
    ) -> None:
        self._settings = settings
        self._tool_dependencies = tuple(tool_dependencies)

    @provide
    def settings(self) -> AgentSettings:
        return self._settings

    @provide
    def workspace(self, settings: AgentSettings) -> Workspace:
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
        if settings.sandbox is None:
            return LocalShellRunner(CommandDefaults(working_directory=workspace.root))
        return create_sandbox(workspace.root, settings.sandbox)

    @provide
    def model_factories(self, settings: AgentSettings) -> _ModelFactories:
        return {model.value: _codex_model_factory(model) for model in settings.models}

    @provide
    def model_switch(
        self,
        settings: AgentSettings,
        model_factories: _ModelFactories,
    ) -> ModelSwitch:
        return ModelSwitch.configurable(
            model_factories,
            default=settings.models[0].value,
            reasoning_efforts=tuple(effort.value for effort in CodexReasoningEffort),
        )

    @provide
    def tool_context(
        self,
        workspace: Workspace,
        command_runner: CommandRunner,
        skills: Skills | None,
        model_switch: ModelSwitch,
    ) -> ToolContext:
        return ToolContext(
            workspace,
            command_runner,
            skills,
            model_switch,
            *self._tool_dependencies,
        )

    @provide
    def agent_components(
        self,
        workspace: Workspace,
        skills: Skills | None,
        model_switch: ModelSwitch,
        tool_context: ToolContext,
    ) -> AgentComponents:
        return AgentComponents(
            workspace=workspace,
            skills=skills,
            models=model_switch,
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
