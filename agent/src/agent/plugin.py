import asyncio
import json
from collections.abc import AsyncIterator, Callable, Mapping
from pathlib import Path
from typing import Any

from agenttoolkit import Skills
from agenttoolkit.builtins import LocalWorkspace
from llmify import (
    AssistantMessage,
    Function,
    Message,
    ToolCall,
    ToolResultMessage,
    UserMessage,
)
from pydantic import BaseModel, ConfigDict

from agent.agent import Agent
from agent.events import TextDelta, ToolCompleted, ToolStarted, TurnCompleted
from agent.models import ModelSwitch
from agent.sandbox import SandboxDefinition
from agent.tools import build_tools
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


class _CaraAgentSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    model: CodexModel = CodexModel.SPARK
    reasoning_effort: CodexReasoningEffort = CodexReasoningEffort.LOW
    workspace_root: Path | None = None
    sandbox_file: Path | None = None
    system_prompt: str | None = None


type _AgentFactory = Callable[[AgentContext], Agent]


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
        agent = self._agent_factory(context)
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
        self._sandbox = _load_sandbox(settings.sandbox_file)
        self._workspace = _create_workspace(settings.workspace_root, self._sandbox)
        skills_root = self._workspace.root / "skills"
        self._skills = Skills.from_dir(skills_root) if skills_root.is_dir() else None

    def __call__(self, context: AgentContext) -> Agent:
        model = create_codex_model(
            self._settings.model,
            reasoning_effort=self._settings.reasoning_effort,
        )
        models = ModelSwitch.single(model, name=self._settings.model.value)
        tools = build_tools(
            injected_dependencies=(models,),
            skills=self._skills,
            workspace=self._workspace,
            sandbox=self._sandbox,
        )
        return Agent(
            models=models,
            tools=tools,
            skills=self._skills,
            system_prompt=self._settings.system_prompt,
            workspace_root=self._workspace.root,
            messages=_context_messages(context),
        )


class _CaraAgentPlugin:
    api_version = AGENT_PLUGIN_API_VERSION

    def create(
        self,
        config: Mapping[str, Any],
        context: AgentPluginContext,
    ) -> _CaraAgentRunner:
        settings = _CaraAgentSettings.model_validate(dict(config))
        return _CaraAgentRunner(context.sessions, _ConfiguredAgentFactory(settings))


def _load_sandbox(path: Path | None) -> SandboxDefinition | None:
    if path is None:
        return None
    return SandboxDefinition.from_yaml(path.expanduser().resolve())


def _create_workspace(
    configured_root: Path | None,
    sandbox: SandboxDefinition | None,
) -> LocalWorkspace:
    root = (
        resolve_workspace_root(configured_root)
        if configured_root is not None or sandbox is None
        else sandbox.resolve_workspace_root()
    )
    max_file_bytes = sandbox.workspace.max_file_bytes if sandbox is not None else None
    return LocalWorkspace(root, max_file_bytes=max_file_bytes)


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


plugin: AgentPlugin = _CaraAgentPlugin()
