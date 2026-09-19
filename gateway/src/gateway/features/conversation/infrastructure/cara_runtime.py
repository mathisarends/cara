import asyncio
import json
from collections.abc import AsyncIterator
from typing import Protocol
from uuid import UUID

from agent.agent import Agent
from agent.events import (
    SteeringApplied,
    TextDelta,
    ToolCompleted,
    ToolStarted,
    TurnCompleted,
)
from agent.factory import AgentFactory
from gateway.agent_runtime.tools import TurnToolDependencies
from gateway.features.conversation.application import (
    AgentEvent,
    AgentRunRequest,
    AgentSessionRef,
    ChatCompleted,
    ChatDelta,
    SessionService,
    ToolCallCompleted,
    ToolCallStarted,
    TurnSteered,
)
from gateway.features.conversation.domain import (
    AssistantMessage as StoredAssistantMessage,
)
from gateway.features.conversation.domain import (
    SessionEntry,
    ToolCall,
    ToolCallSequence,
    ToolCallState,
)
from gateway.features.conversation.domain import (
    UserMessage as StoredUserMessage,
)
from gateway.shared import UnitOfWork
from llm import (
    AssistantMessage,
    Message,
    ToolResultMessage,
    UserMessage,
)
from llm import (
    ToolCall as LlmToolCall,
)


class _SandboxPrewarmer(Protocol):
    async def ensure(self) -> None: ...


class CaraAgentRuntime:
    def __init__(
        self,
        sessions: UnitOfWork[SessionService],
        factory: AgentFactory,
        sandbox: _SandboxPrewarmer,
        tool_dependencies: TurnToolDependencies,
    ) -> None:
        self._sessions = sessions
        self._factory = factory
        self._sandbox = sandbox
        self._tool_dependencies = tool_dependencies
        self._agents: dict[UUID, Agent] = {}
        self._active_sessions: set[UUID] = set()
        self._registry_lock = asyncio.Lock()

    async def prepare(self, session: AgentSessionRef) -> None:
        await asyncio.gather(
            self._get_or_create_agent(session),
            self._sandbox.ensure(),
        )

    async def run(self, request: AgentRunRequest) -> AsyncIterator[AgentEvent]:
        agent = await self._get_or_create_agent(
            request.session,
            input_id=request.input_id,
        )
        self._active_sessions.add(request.session.id)
        try:
            events = await agent.start_turn(request.input)
            async for event in events:
                yield _runtime_event(event)
        finally:
            self._active_sessions.discard(request.session.id)

    async def steer(self, session: AgentSessionRef, text: str) -> None:
        agent = self._agents.get(session.id)
        if agent is not None and session.id in self._active_sessions:
            await agent.steer(text)

    async def finish(self, session: AgentSessionRef) -> None:
        async with self._registry_lock:
            agent = self._agents.pop(session.id, None)
        if agent is not None:
            self._active_sessions.discard(session.id)
            await agent.aclose()

    async def close(self) -> None:
        async with self._registry_lock:
            agents = tuple(self._agents.values())
            self._agents.clear()
            self._active_sessions.clear()
        if agents:
            await asyncio.gather(
                *(agent.aclose() for agent in agents),
                return_exceptions=True,
            )

    async def _get_or_create_agent(
        self,
        session: AgentSessionRef,
        *,
        input_id: UUID | None = None,
    ) -> Agent:
        async with self._registry_lock:
            agent = self._agents.get(session.id)
            if agent is not None:
                return agent
            messages = await _context_messages(self._sessions, session.id, input_id)
            agent = await self._factory.create(
                messages,
                tool_dependencies=self._tool_dependencies.create(session),
            )
            self._agents[session.id] = agent
            return agent


async def _context_messages(
    sessions: UnitOfWork[SessionService],
    session_id: UUID,
    input_id: UUID | None,
) -> list[Message]:
    async with sessions() as service:
        session = await service.get(session_id)

    messages: list[Message] = []
    for entry in session.entries:
        if entry.id == input_id:
            return messages
        messages.extend(_entry_messages(entry))
    if input_id is None:
        return messages
    raise ValueError(f"Input {input_id} does not belong to session {session_id}")


def _entry_messages(entry: SessionEntry) -> list[Message]:
    if isinstance(entry, StoredUserMessage):
        return [UserMessage(content=entry.content)]
    if isinstance(entry, StoredAssistantMessage):
        return [AssistantMessage(content=entry.content)]
    if isinstance(entry, ToolCallSequence):
        calls = [_llm_tool_call(call) for call in entry.calls]
        return [
            AssistantMessage(content="", tool_calls=tuple(calls)),
            *(_llm_tool_result(call) for call in entry.calls),
        ]
    raise TypeError(f"Unsupported session entry: {type(entry).__name__}")


def _llm_tool_call(call: ToolCall) -> LlmToolCall:
    if call.state is ToolCallState.PENDING:
        raise ValueError(f"Tool call {call.call_id} is still pending")
    return LlmToolCall(
        id=call.call_id,
        name=call.function_name,
        arguments=json.dumps(call.function_arguments, ensure_ascii=False),
    )


def _llm_tool_result(call: ToolCall) -> ToolResultMessage:
    value = call.error if call.state is ToolCallState.FAILED else call.result
    content = (
        "Tool completed successfully."
        if value is None
        else value
        if isinstance(value, str)
        else json.dumps(value, ensure_ascii=False, sort_keys=True)
    )
    return ToolResultMessage(
        tool_call_id=call.call_id,
        tool_name=call.function_name,
        content=content,
        is_error=call.state is ToolCallState.FAILED,
    )


def _runtime_event(event: object) -> AgentEvent:
    match event:
        case TextDelta():
            return ChatDelta(event.text)
        case TurnCompleted():
            return ChatCompleted(event.text, event.finish_reason)
        case SteeringApplied():
            return TurnSteered(event.text)
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
