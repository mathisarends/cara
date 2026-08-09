import json
from collections.abc import Callable
from pathlib import Path

from agenttoolkit import Skills, Tools
from llmify import (
    ChatInvokeCompletion,
    ChatModel,
    ChatOpenAIResponses,
    LLMifyError,
    OpenAIResponsesState,
    OpenAIResponsesStreamEnd,
    StreamEnd,
    StreamTextDelta,
    ToolCall,
    ToolResultMessage,
)
from transitbus import EventBus

from cara.events import AssistantTurnStarted, ToolCallFinished, ToolCallStarted
from cara.prompt import Conversation, SystemPromptComposer

_MAX_TOOL_ROUNDS = 8


class Agent:
    def __init__(
        self,
        *,
        llm: ChatModel,
        tools: Tools,
        prompt_root: Path,
        skills: Skills | None = None,
        system_prompt: str | None = None,
        override_system_prompt: str | None = None,
        extend_system_prompt: str | None = None,
        event_bus: EventBus | None = None,
    ) -> None:
        self._llm = llm
        self._tools = tools
        self._conversation = Conversation(
            system_prompt=SystemPromptComposer(
                root=prompt_root,
                system_prompt=system_prompt,
                override_system_prompt=override_system_prompt,
                extend_system_prompt=extend_system_prompt,
                skills=skills,
            ),
        )
        self._responses_state: OpenAIResponsesState | None = None
        self._event_bus = event_bus

    async def respond(
        self,
        text: str,
        *,
        on_text_delta: Callable[[str], None] | None = None,
        on_tool_call: Callable[[str, dict[str, object]], None] | None = None,
        on_tool_result: Callable[[str, str], None] | None = None,
    ) -> str:
        """Add a user turn, run the model and tools, and return the final answer.

        When ``on_text_delta`` is provided, model text is streamed to it as it arrives.
        """
        text = text.strip()
        if not text:
            return ""

        await self._dispatch(AssistantTurnStarted())
        self._conversation.add_user(text)
        if on_text_delta is None:
            answer = await self._generate_answer(
                on_tool_call=on_tool_call,
                on_tool_result=on_tool_result,
            )
        else:
            answer = await self._generate_streaming_answer(
                on_text_delta=on_text_delta,
                on_tool_call=on_tool_call,
                on_tool_result=on_tool_result,
            )
        self._conversation.add_assistant(answer)
        return answer

    async def _generate_streaming_answer(
        self,
        *,
        on_text_delta: Callable[[str], None],
        on_tool_call: Callable[[str, dict[str, object]], None] | None,
        on_tool_result: Callable[[str, str], None] | None,
    ) -> str:
        if isinstance(self._llm, ChatOpenAIResponses):
            return await self._generate_streaming_responses_answer(
                on_text_delta=on_text_delta,
                on_tool_call=on_tool_call,
                on_tool_result=on_tool_result,
            )

        while True:
            end: StreamEnd | None = None
            async for event in self._llm.stream(
                self._conversation.to_llm_messages(),
                tools=self._tools.get_schema("openai"),
            ):
                if isinstance(event, StreamTextDelta):
                    on_text_delta(event.delta)
                elif isinstance(event, StreamEnd):
                    end = event

            if end is None:
                raise RuntimeError("The model stream ended without a terminal event.")

            for tool_call in end.tool_calls:
                await self._execute_tool(
                    tool_call,
                    on_tool_call=on_tool_call,
                    on_tool_result=on_tool_result,
                )
            if not end.tool_calls:
                return end.completion.strip()

    async def _generate_streaming_responses_answer(
        self,
        *,
        on_text_delta: Callable[[str], None],
        on_tool_call: Callable[[str, dict[str, object]], None] | None,
        on_tool_result: Callable[[str, str], None] | None,
    ) -> str:
        messages = (
            self._conversation.to_llm_messages()
            if self._responses_state is None
            else self._conversation.to_current_turn_messages()
        )
        state = self._responses_state

        for round_index in range(_MAX_TOOL_ROUNDS + 1):
            end: OpenAIResponsesStreamEnd | None = None
            async for event in self._llm.stream(
                messages,
                tools=self._tools.get_schema("openai"),
                provider_state=state,
            ):
                if isinstance(event, StreamTextDelta):
                    on_text_delta(event.delta)
                elif isinstance(event, OpenAIResponsesStreamEnd):
                    end = event

            if end is None:
                raise RuntimeError(
                    "The Responses stream ended without a terminal event."
                )

            state = end.provider_state
            if not end.tool_calls:
                self._responses_state = state
                return end.completion.strip()

            if round_index == _MAX_TOOL_ROUNDS:
                raise LLMifyError(
                    f"Tool loop exceeded max_tool_rounds={_MAX_TOOL_ROUNDS}."
                )

            tool_results: list[ToolResultMessage] = []
            for tool_call in end.tool_calls:
                content = await self._execute_tool(
                    tool_call,
                    on_tool_call=on_tool_call,
                    on_tool_result=on_tool_result,
                )
                tool_results.append(
                    ToolResultMessage(tool_call_id=tool_call.id, content=content)
                )
            messages = tool_results

        raise AssertionError("unreachable")

    async def _execute_tool(
        self,
        tool_call: ToolCall,
        *,
        on_tool_call: Callable[[str, dict[str, object]], None] | None,
        on_tool_result: Callable[[str, str], None] | None,
    ) -> str:
        self._conversation.add_tool_call(tool_call)
        name = tool_call.function.name
        arguments = json.loads(tool_call.function.arguments or "{}")
        if on_tool_call is not None:
            on_tool_call(name, arguments)

        await self._dispatch(ToolCallStarted(tool_name=name))
        try:
            result = await self._tools.execute(name, arguments)
        finally:
            await self._dispatch(ToolCallFinished(tool_name=name))
        content = "Tool completed successfully." if result is None else str(result)
        if on_tool_result is not None:
            on_tool_result(name, content)
        self._conversation.add_tool_result(tool_call.id, content)
        return content

    async def _generate_answer(
        self,
        *,
        on_tool_call: Callable[[str, dict[str, object]], None] | None,
        on_tool_result: Callable[[str, str], None] | None,
    ) -> str:
        if isinstance(self._llm, ChatOpenAIResponses):
            return await self._generate_responses_answer(
                on_tool_call=on_tool_call,
                on_tool_result=on_tool_result,
            )

        while True:
            completion = await self._llm.invoke(
                self._conversation.to_llm_messages(),
                tools=self._tools.get_schema("openai"),
            )
            answer, called_tools = await self._resolve_completion(
                completion,
                on_tool_call=on_tool_call,
                on_tool_result=on_tool_result,
            )
            if not called_tools:
                return answer

    async def _generate_responses_answer(
        self,
        *,
        on_tool_call: Callable[[str, dict[str, object]], None] | None,
        on_tool_result: Callable[[str, str], None] | None,
    ) -> str:
        messages = (
            self._conversation.to_llm_messages()
            if self._responses_state is None
            else self._conversation.to_current_turn_messages()
        )

        async def execute_tool(tool_call: ToolCall) -> str:
            return await self._execute_tool(
                tool_call,
                on_tool_call=on_tool_call,
                on_tool_result=on_tool_result,
            )

        completion = await self._llm.invoke_with_tools(
            messages,
            tools=self._tools.get_schema("openai"),
            tool_executor=execute_tool,
            provider_state=self._responses_state,
        )
        self._responses_state = completion.provider_state
        return completion.completion.strip()

    async def _resolve_completion(
        self,
        completion: ChatInvokeCompletion[str],
        *,
        on_tool_call: Callable[[str, dict[str, object]], None] | None,
        on_tool_result: Callable[[str, str], None] | None,
    ) -> tuple[str, bool]:
        answer = completion.completion.strip()
        for tool_call in completion.tool_calls:
            await self._execute_tool(
                tool_call,
                on_tool_call=on_tool_call,
                on_tool_result=on_tool_result,
            )

        return answer, bool(completion.tool_calls)

    async def _dispatch(
        self, event: AssistantTurnStarted | ToolCallStarted | ToolCallFinished
    ) -> None:
        if self._event_bus is not None:
            await self._event_bus.dispatch(event)
