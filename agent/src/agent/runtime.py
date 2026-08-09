import json
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from agenttoolkit import Tools
from llmify import (
    AssistantMessage,
    ChatModel,
    Function,
    LLMifyError,
    Message,
    OpenAIResponsesStreamEnd,
    StreamEnd,
    StreamTextDelta,
    SystemMessage,
    ToolCall,
    ToolResultMessage,
    UserMessage,
)

from agent.prompt import SystemPromptComposer

_MAX_TOOL_ROUNDS = 8


@dataclass(frozen=True, slots=True)
class StoredToolCall:
    call_id: str
    name: str
    arguments: dict[str, object]
    result: object = None
    error: str | None = None


class AgentContext:
    """Conversation history and system context consumed by the runtime."""

    def __init__(self, system_prompt: SystemPromptComposer) -> None:
        self._system_prompt = system_prompt
        self._messages: list[Message] = []

    def add_user_message(self, content: str) -> None:
        self._messages.append(UserMessage(content=content))

    def add_assistant_message(self, content: str) -> None:
        self._messages.append(AssistantMessage(content=content))

    def add_tool_calls(self, calls: Sequence[StoredToolCall]) -> None:
        self._messages.append(
            AssistantMessage(
                tool_calls=[
                    ToolCall(
                        id=call.call_id,
                        function=Function(
                            name=call.name,
                            arguments=json.dumps(call.arguments),
                        ),
                    )
                    for call in calls
                ]
            )
        )
        self._messages.extend(
            ToolResultMessage(
                tool_call_id=call.call_id,
                content=_stored_tool_result(call),
            )
            for call in calls
        )

    def to_llm_messages(self) -> list[Message]:
        return [SystemMessage(content=self._system_prompt.render()), *self._messages]


class AgentCallbacks(Protocol):
    async def on_text_delta(self, text: str) -> None: ...

    async def on_tool_call_started(
        self,
        call_id: str,
        name: str,
        arguments: dict[str, object],
    ) -> None: ...

    async def on_tool_call_completed(
        self,
        call_id: str,
        name: str,
        result: object,
        *,
        is_error: bool,
    ) -> None: ...

    async def on_completed(self, text: str, finish_reason: str) -> None: ...


class AgentRuntime:
    """Runs a complete streamed model/tool loop for an assembled context."""

    def __init__(self, *, llm: ChatModel, tools: Tools) -> None:
        self._llm = llm
        self._tools = tools

    async def run(
        self,
        context: AgentContext,
        callbacks: AgentCallbacks,
    ) -> None:
        messages = context.to_llm_messages()
        for round_index in range(_MAX_TOOL_ROUNDS + 1):
            end: StreamEnd | OpenAIResponsesStreamEnd | None = None
            async for event in self._llm.stream(
                messages=messages,
                tools=self._tools.get_schema("openai"),
            ):
                if isinstance(event, StreamTextDelta):
                    if event.delta:
                        await callbacks.on_text_delta(event.delta)
                elif isinstance(event, (OpenAIResponsesStreamEnd, StreamEnd)):
                    end = event

            if end is None:
                raise LLMifyError("The model stream ended without a terminal event.")

            if not end.tool_calls:
                await callbacks.on_completed(
                    end.completion or "",
                    end.stop_reason or "stop",
                )
                return

            if round_index == _MAX_TOOL_ROUNDS:
                raise LLMifyError(
                    f"Tool loop exceeded max_tool_rounds={_MAX_TOOL_ROUNDS}."
                )

            tool_results = await self._execute_tools(end.tool_calls, callbacks)
            messages.extend(
                [AssistantMessage(tool_calls=end.tool_calls), *tool_results]
            )

        raise AssertionError("unreachable")

    async def _execute_tools(
        self,
        tool_calls: list[ToolCall],
        callbacks: AgentCallbacks,
    ) -> list[ToolResultMessage]:
        calls = [(_tool_arguments(call), call) for call in tool_calls]
        for arguments, call in calls:
            await callbacks.on_tool_call_started(
                call.id,
                call.function.name,
                arguments,
            )

        results: list[ToolResultMessage] = []
        for arguments, call in calls:
            name = call.function.name
            try:
                result = await self._tools.execute(name, arguments)
            except Exception as error:
                await callbacks.on_tool_call_completed(
                    call.id,
                    name,
                    str(error),
                    is_error=True,
                )
                raise

            await callbacks.on_tool_call_completed(
                call.id,
                name,
                result,
                is_error=False,
            )
            results.append(
                ToolResultMessage(
                    tool_call_id=call.id,
                    content=_render_tool_value(result),
                )
            )
        return results


def _tool_arguments(tool_call: ToolCall) -> dict[str, object]:
    arguments = json.loads(tool_call.function.arguments or "{}")
    if not isinstance(arguments, dict):
        raise ValueError(
            f"Tool arguments for '{tool_call.function.name}' must be an object."
        )
    return arguments


def _stored_tool_result(call: StoredToolCall) -> str:
    if call.error is not None:
        return f"Tool failed: {call.error or 'unknown error'}"
    return _render_tool_value(call.result)


def _render_tool_value(value: object) -> str:
    if value is None:
        return "Tool completed successfully."
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, sort_keys=True)
