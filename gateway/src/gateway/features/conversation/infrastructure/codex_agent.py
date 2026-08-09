import json
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from uuid import UUID

from agenttoolkit import Tools
from llmify import (
    AssistantMessage as LLMAssistantMessage,
)
from llmify import (
    Function,
    LLMifyError,
    OpenAIResponsesStreamEnd,
    StreamEnd,
    StreamTextDelta,
    ToolCall,
    ToolResultMessage,
)
from llmify import (
    Message as LLMMessage,
)
from llmify import (
    UserMessage as LLMUserMessage,
)

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

_MAX_TOOL_ROUNDS = 8
type ToolFactory = Callable[[], AbstractAsyncContextManager[Tools]]


class CodexAgentRunner(AgentRunner):
    def __init__(
        self,
        *,
        sessions: SessionRepository,
        llm,
        tool_factory: ToolFactory,
    ) -> None:
        self._sessions = sessions
        self._llm = llm
        self._tool_factory = tool_factory

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

        async with self._tool_factory() as tools:
            await self._run_tool_loop(
                _session_messages(session.entries),
                tools,
                event_bus,
            )

    async def _run_tool_loop(
        self,
        messages: list[LLMMessage],
        tools: Tools,
        event_bus: AgentEventBus,
    ) -> None:
        for round_index in range(_MAX_TOOL_ROUNDS + 1):
            end: StreamEnd | OpenAIResponsesStreamEnd | None = None
            async for event in self._llm.stream(
                messages=messages,
                tools=tools.get_schema("openai"),
            ):
                if isinstance(event, StreamTextDelta):
                    if event.delta:
                        await event_bus.dispatch(ChatDelta(text=event.delta))
                elif isinstance(event, (OpenAIResponsesStreamEnd, StreamEnd)):
                    end = event

            if end is None:
                raise LLMifyError("The model stream ended without a terminal event.")

            if not end.tool_calls:
                await event_bus.dispatch(
                    ChatCompleted(
                        text=end.completion or "",
                        finish_reason=end.stop_reason,
                    )
                )
                return

            if round_index == _MAX_TOOL_ROUNDS:
                raise LLMifyError(
                    f"Tool loop exceeded max_tool_rounds={_MAX_TOOL_ROUNDS}."
                )

            tool_results = await self._execute_tools(
                end.tool_calls,
                tools,
                event_bus,
            )
            messages.extend(
                [LLMAssistantMessage(tool_calls=end.tool_calls), *tool_results]
            )

        raise AssertionError("unreachable")

    async def _execute_tools(
        self,
        tool_calls: list[ToolCall],
        tools: Tools,
        event_bus: AgentEventBus,
    ) -> list[ToolResultMessage]:
        calls = [(_tool_arguments(call), call) for call in tool_calls]
        for arguments, call in calls:
            await event_bus.dispatch(
                ToolCallStarted(
                    call_id=call.id,
                    name=call.function.name,
                    arguments=arguments,
                )
            )

        results: list[ToolResultMessage] = []
        for arguments, call in calls:
            name = call.function.name
            try:
                result = await tools.execute(name, arguments)
            except Exception as error:
                await event_bus.dispatch(
                    ToolCallCompleted(
                        call_id=call.id,
                        name=name,
                        result=str(error),
                        is_error=True,
                    )
                )
                raise

            await event_bus.dispatch(
                ToolCallCompleted(
                    call_id=call.id,
                    name=name,
                    result=result,
                )
            )
            results.append(
                ToolResultMessage(
                    tool_call_id=call.id,
                    content=_render_tool_value(result),
                )
            )
        return results


def _session_messages(entries: tuple[SessionEntry, ...]) -> list[LLMMessage]:
    messages: list[LLMMessage] = []
    for entry in entries:
        if isinstance(entry, UserMessage):
            messages.append(LLMUserMessage(content=entry.content))
        elif isinstance(entry, AssistantMessage):
            messages.append(LLMAssistantMessage(content=entry.content))
        elif isinstance(entry, ToolCallSequence):
            messages.append(
                LLMAssistantMessage(
                    tool_calls=[
                        ToolCall(
                            id=call.call_id,
                            function=Function(
                                name=call.function_name,
                                arguments=json.dumps(call.function_arguments),
                            ),
                        )
                        for call in entry.calls
                    ]
                )
            )
            messages.extend(
                ToolResultMessage(
                    tool_call_id=call.call_id,
                    content=_stored_tool_result(call.state, call.result, call.error),
                )
                for call in entry.calls
            )
    return messages


def _tool_arguments(tool_call: ToolCall) -> dict[str, object]:
    arguments = json.loads(tool_call.function.arguments or "{}")
    if not isinstance(arguments, dict):
        raise ValueError(
            f"Tool arguments for '{tool_call.function.name}' must be an object."
        )
    return arguments


def _stored_tool_result(
    state: ToolCallState,
    result: object,
    error: str | None,
) -> str:
    if state is ToolCallState.PENDING:
        raise ValueError("Cannot send a pending tool call back to the model.")
    if state is ToolCallState.FAILED:
        return f"Tool failed: {error or 'unknown error'}"
    return _render_tool_value(result)


def _render_tool_value(value: object) -> str:
    if value is None:
        return "Tool completed successfully."
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, sort_keys=True)
