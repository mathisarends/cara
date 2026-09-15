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
from agent.tools.handler import GatewayConnection, GatewayReminders
from gateway.features.conversation.application import (
    AgentEvent,
    AgentRunRequest,
    AgentSessionRef,
    ChatCompleted,
    ChatDelta,
    ToolCallCompleted,
    ToolCallStarted,
    TurnSteered,
)
from gateway.features.conversation.domain import (
    AssistantMessage as StoredAssistantMessage,
)
from gateway.features.conversation.domain import (
    SessionEntry,
    SessionNotFoundError,
    SessionRepository,
    ToolCall,
    ToolCallSequence,
    ToolCallState,
)
from gateway.features.conversation.domain import (
    UserMessage as StoredUserMessage,
)
from llm import (
    AssistantMessage,
    ChatModel,
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
        sessions: SessionRepository,
        factory: AgentFactory,
        sandbox: _SandboxPrewarmer,
    ) -> None:
        self._sessions = sessions
        self._factory = factory
        self._sandbox = sandbox
        self._active_agents: dict[UUID, Agent] = {}
        self._preparations: dict[UUID, asyncio.Task[ChatModel]] = {}
        self._preparation_lock = asyncio.Lock()

    async def prepare(self, session: AgentSessionRef) -> None:
        async with self._preparation_lock:
            preparation = self._preparations.get(session.id)
            if preparation is None:
                preparation = asyncio.create_task(
                    self._factory.prewarm_model(),
                    name=f"cara-model-prewarm-{session.id}",
                )
                self._preparations[session.id] = preparation
        try:
            await asyncio.gather(
                asyncio.shield(preparation),
                self._sandbox.ensure(),
            )
        except BaseException:
            async with self._preparation_lock:
                if self._preparations.get(session.id) is preparation:
                    self._preparations.pop(session.id)
            raise

    async def run(self, request: AgentRunRequest) -> AsyncIterator[AgentEvent]:
        preparation = await self._take_preparation(request.session.id)
        initial_model = await preparation if preparation is not None else None
        messages = await _context_messages(
            self._sessions,
            request.session.id,
            request.input_id,
        )
        try:
            agent = await self._factory.create(
                messages,
                tool_dependencies=_turn_tool_dependencies(request),
                initial_model=initial_model,
            )
        except BaseException:
            if initial_model is not None:
                await initial_model.aclose()
            raise
        self._active_agents[request.session.id] = agent
        try:
            events = await agent.start_turn(request.input)
            async for event in events:
                yield _runtime_event(event)
        finally:
            if self._active_agents.get(request.session.id) is agent:
                del self._active_agents[request.session.id]
            await agent.aclose()

    async def steer(self, session: AgentSessionRef, text: str) -> None:
        agent = self._active_agents.get(session.id)
        if agent is not None:
            await agent.steer(text)

    async def finish(self, session: AgentSessionRef) -> None:
        preparation = await self._take_preparation(session.id)
        if preparation is not None:
            model = await preparation
            await model.aclose()

    async def close(self) -> None:
        async with self._preparation_lock:
            preparations = tuple(self._preparations.values())
            self._preparations.clear()
        prepared_models = await asyncio.gather(*preparations, return_exceptions=True)
        await asyncio.gather(
            *(
                model.aclose()
                for model in prepared_models
                if not isinstance(model, BaseException)
            )
        )
        agents = tuple(self._active_agents.values())
        if agents:
            await asyncio.gather(*(agent.aclose() for agent in agents))

    async def _take_preparation(
        self,
        session_id: UUID,
    ) -> asyncio.Task[ChatModel] | None:
        async with self._preparation_lock:
            return self._preparations.pop(session_id, None)


async def _context_messages(
    sessions: SessionRepository,
    session_id: UUID,
    input_id: UUID | None,
) -> list[Message]:
    session = await sessions.find_by_id(session_id)
    if session is None:
        raise SessionNotFoundError(session_id)

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
        call.call_id,
        call.function_name,
        json.dumps(call.function_arguments, ensure_ascii=False),
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


def _turn_tool_dependencies(request: AgentRunRequest) -> tuple[object, ...]:
    connection = GatewayConnection()
    if connection.token is None:
        return ()
    return (GatewayReminders(connection, session_id=request.session.id),)
