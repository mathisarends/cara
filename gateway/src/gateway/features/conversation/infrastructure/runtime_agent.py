from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from pathlib import Path
from uuid import UUID

from agenttoolkit import Tools
from llmify import ChatModel

from agent import AgentContext, AgentRuntime, StoredToolCall, SystemPromptComposer
from gateway.features.conversation.application import AgentEventBus, AgentRunner
from gateway.features.conversation.domain import (
    AssistantMessage,
    ChatCompleted,
    ChatDelta,
    SessionEntry,
    SessionNotFoundError,
    SessionRepository,
    ToolCallCompleted,
    ToolCallSequence,
    ToolCallStarted,
    ToolCallState,
    UserMessage,
)

type ToolFactory = Callable[[], AbstractAsyncContextManager[Tools]]


class RuntimeAgentRunner(AgentRunner):
    def __init__(
        self,
        *,
        sessions: SessionRepository,
        llm: ChatModel,
        tool_factory: ToolFactory,
        prompt_root: Path,
    ) -> None:
        self._sessions = sessions
        self._llm = llm
        self._tool_factory = tool_factory
        self._prompt_root = prompt_root

    async def run(
        self,
        session_id: UUID,
        metadata: dict[str, object],
        event_bus: AgentEventBus,
    ) -> None:
        del metadata
        session = await self._sessions.find_by_id(session_id)
        if session is None:
            raise SessionNotFoundError(session_id)

        context = _agent_context(session.entries, self._prompt_root)
        callbacks = _GatewayCallbacks(event_bus)
        async with self._tool_factory() as tools:
            await AgentRuntime(llm=self._llm, tools=tools).run(context, callbacks)


class _GatewayCallbacks:
    def __init__(self, event_bus: AgentEventBus) -> None:
        self._event_bus = event_bus

    async def on_text_delta(self, text: str) -> None:
        await self._event_bus.dispatch(ChatDelta(text=text))

    async def on_tool_call_started(
        self,
        call_id: str,
        name: str,
        arguments: dict[str, object],
    ) -> None:
        await self._event_bus.dispatch(
            ToolCallStarted(call_id=call_id, name=name, arguments=arguments)
        )

    async def on_tool_call_completed(
        self,
        call_id: str,
        name: str,
        result: object,
        *,
        is_error: bool,
    ) -> None:
        await self._event_bus.dispatch(
            ToolCallCompleted(
                call_id=call_id,
                name=name,
                result=result,
                is_error=is_error,
            )
        )

    async def on_completed(self, text: str, finish_reason: str) -> None:
        await self._event_bus.dispatch(
            ChatCompleted(text=text, finish_reason=finish_reason)
        )


def _agent_context(
    entries: tuple[SessionEntry, ...],
    prompt_root: Path,
) -> AgentContext:
    context = AgentContext(SystemPromptComposer(root=prompt_root))
    for entry in entries:
        if isinstance(entry, UserMessage):
            context.add_user_message(entry.content)
        elif isinstance(entry, AssistantMessage):
            context.add_assistant_message(entry.content)
        elif isinstance(entry, ToolCallSequence):
            context.add_tool_calls(
                [
                    StoredToolCall(
                        call_id=call.call_id,
                        name=call.function_name,
                        arguments=call.function_arguments,
                        result=call.result,
                        error=_tool_error(call.state, call.error),
                    )
                    for call in entry.calls
                ]
            )
    return context


def _tool_error(state: ToolCallState, error: str | None) -> str | None:
    if state is ToolCallState.PENDING:
        raise ValueError("Cannot send a pending tool call back to the model.")
    if state is ToolCallState.FAILED:
        return error or "unknown error"
    return None
