import asyncio
import json
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from pathlib import Path
from typing import Any, cast

from agenttoolkit import DependencyProvider, Skills, ToolContext, provide
from agenttoolkit.builtins import (
    CommandDefaults,
    CommandRunner,
    LocalShellRunner,
    LocalWorkspace,
    Workspace,
)
from agenttoolkit.dependency import DependencyContainer
from llmify import (
    AssistantMessage,
    ChatModel,
    Function,
    Message,
    ToolCall,
    ToolResultMessage,
    UserMessage,
)
from pydantic import BaseModel, ConfigDict, Field, field_validator

from agent.agent import Agent
from agent.events import TextDelta, ToolCompleted, ToolStarted, TurnCompleted
from agent.models import ModelSwitch
from agent.sandbox import SandboxDefinition, create_sandbox
from agent.tools import build_tools
from agent.tools.dependency_provider import BuiltinDependencies
from agent.workspace import resolve_workspace_root
from agent_plugin_api import (
    AGENT_PLUGIN_API_VERSION,
    AgentAssistantMessage,
    AgentContext,
    AgentEvent,
    AgentPlugin,
    AgentPluginContext,
    AgentRunRequest,
    AgentSessionReader,
    AgentToolCall,
    AgentToolCallSequence,
    AgentToolCallState,
    AgentUserMessage,
    ChatCompleted,
    ChatDelta,
    ToolCallCompleted,
    ToolCallStarted,
)
from llm import CodexModel, CodexReasoningEffort, create_codex_model


class _WorkspaceSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    root: Path | None = None
    max_file_bytes: int | None = Field(default=None, gt=0)


class _CaraAgentSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    models: tuple[CodexModel, ...] = Field(
        default=(CodexModel.SPARK,),
        min_length=1,
    )
    workspace: _WorkspaceSettings = Field(default_factory=_WorkspaceSettings)
    sandbox: SandboxDefinition | None = None
    system_prompt: str | None = None

    @field_validator("models")
    @classmethod
    def _models_must_be_unique(
        cls,
        models: tuple[CodexModel, ...],
    ) -> tuple[CodexModel, ...]:
        if len(set(models)) != len(models):
            raise ValueError("models must not contain duplicates")
        return models


type _ModelFactories = dict[str, Callable[[str | None], ChatModel]]
type _AgentFactory = Callable[[AgentContext], Awaitable[Agent]]

_SKILLS_DEPENDENCY = cast(type[Skills | None], Skills | None)


class _CaraAgentRunner:
    def __init__(
        self,
        sessions: AgentSessionReader,
        agent_factory: _AgentFactory,
    ) -> None:
        self._sessions = sessions
        self._agent_factory = agent_factory
        self._active_agents: set[Agent] = set()

    async def run(self, request: AgentRunRequest) -> AsyncIterator[AgentEvent]:
        context = await self._sessions.context_for_turn(
            request.session.id,
            request.input_id,
        )
        agent = await self._agent_factory(context)
        self._active_agents.add(agent)
        try:
            events = await agent.start_turn(request.input)
            async for event in events:
                yield _plugin_event(event)
        finally:
            self._active_agents.discard(agent)
            await agent.interrupt()

    async def close(self) -> None:
        agents = tuple(self._active_agents)
        if agents:
            await asyncio.gather(*(agent.interrupt() for agent in agents))


class _ConfiguredAgentFactory:
    def __init__(self, settings: _CaraAgentSettings) -> None:
        self._settings = settings

    async def __call__(self, context: AgentContext) -> Agent:
        container = DependencyContainer(
            _ConfiguredDependencies(self._settings),
            BuiltinDependencies(),
        )
        settings = await container.get(_CaraAgentSettings)
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
            messages=_context_messages(context),
        )


class _ConfiguredDependencies(DependencyProvider):
    def __init__(self, settings: _CaraAgentSettings) -> None:
        self._settings = settings

    @provide
    def settings(self) -> _CaraAgentSettings:
        return self._settings

    @provide
    def workspace(self, settings: _CaraAgentSettings) -> Workspace:
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
        settings: _CaraAgentSettings,
        workspace: Workspace,
    ) -> CommandRunner:
        if settings.sandbox is None:
            return LocalShellRunner(CommandDefaults(working_directory=workspace.root))
        return create_sandbox(workspace.root, settings.sandbox)

    @provide
    def model_factories(self, settings: _CaraAgentSettings) -> _ModelFactories:
        return {model.value: _codex_model_factory(model) for model in settings.models}

    @provide
    def model_switch(
        self,
        settings: _CaraAgentSettings,
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
        return ToolContext(workspace, command_runner, skills, model_switch)


class _CaraAgentPlugin:
    api_version = AGENT_PLUGIN_API_VERSION

    def create(
        self,
        config: Mapping[str, Any],
        context: AgentPluginContext,
    ) -> _CaraAgentRunner:
        settings = _CaraAgentSettings.model_validate(dict(config))
        return _CaraAgentRunner(context.sessions, _ConfiguredAgentFactory(settings))


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


def _context_messages(context: AgentContext) -> list[Message]:
    messages: list[Message] = []
    for entry in context.entries:
        match entry:
            case AgentUserMessage():
                messages.append(UserMessage(content=entry.content))
            case AgentAssistantMessage():
                messages.append(AssistantMessage(content=entry.content))
            case AgentToolCallSequence():
                calls = [_llm_tool_call(call) for call in entry.calls]
                messages.append(AssistantMessage(content="", tool_calls=calls))
                messages.extend(_llm_tool_result(call) for call in entry.calls)
    return messages


def _llm_tool_call(call: AgentToolCall) -> ToolCall:
    return ToolCall(
        id=call.call_id,
        function=Function(
            name=call.name,
            arguments=json.dumps(call.arguments, ensure_ascii=False),
        ),
    )


def _llm_tool_result(call: AgentToolCall) -> ToolResultMessage:
    value = call.error if call.state is AgentToolCallState.FAILED else call.result
    content = (
        "Tool completed successfully."
        if value is None
        else value
        if isinstance(value, str)
        else json.dumps(value, ensure_ascii=False, sort_keys=True)
    )
    return ToolResultMessage(tool_call_id=call.call_id, content=content)


def _plugin_event(event: object) -> AgentEvent:
    match event:
        case TextDelta():
            return ChatDelta(event.text)
        case TurnCompleted():
            return ChatCompleted(event.text, event.finish_reason)
        case ToolStarted():
            return ToolCallStarted(event.call_id, event.name, event.arguments)
        case ToolCompleted():
            return ToolCallCompleted(
                event.call_id,
                event.name,
                event.result,
                event.is_error,
            )
    raise TypeError(f"Unsupported Cara agent event: {type(event).__name__}")


def create_plugin() -> AgentPlugin:
    return _CaraAgentPlugin()
