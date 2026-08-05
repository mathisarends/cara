import json
from collections.abc import Callable
from pathlib import Path

from agenttoolkit import Skills, Tools
from llmify import (
    ChatInvokeCompletion,
    ChatModel,
    ChatOpenAIResponses,
    OpenAIResponsesState,
    ToolCall,
)

from cara.prompt import Conversation, SystemPromptComposer


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

    async def respond(
        self,
        text: str,
        *,
        on_tool_call: Callable[[str, dict[str, object]], None] | None = None,
        on_tool_result: Callable[[str, str], None] | None = None,
    ) -> str:
        """Add a user turn, run the model and tools, and return the final answer."""
        text = text.strip()
        if not text:
            return ""

        self._conversation.add_user(text)
        answer = await self._generate_answer(
            on_tool_call=on_tool_call,
            on_tool_result=on_tool_result,
        )
        self._conversation.add_assistant(answer)
        return answer

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
            self._conversation.add_tool_call(tool_call)
            name = tool_call.function.name
            arguments = json.loads(tool_call.function.arguments or "{}")
            if on_tool_call is not None:
                on_tool_call(name, arguments)

            result = await self._tools.execute(name, arguments)
            content = "Tool completed successfully." if result is None else str(result)
            if on_tool_result is not None:
                on_tool_result(name, content)
            self._conversation.add_tool_result(tool_call.id, content)
            return content

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
            self._conversation.add_tool_call(tool_call)
            name = tool_call.function.name
            arguments = json.loads(tool_call.function.arguments or "{}")
            if on_tool_call is not None:
                on_tool_call(name, arguments)

            result = await self._tools.execute(name, arguments)
            content = "Tool completed successfully." if result is None else str(result)
            if on_tool_result is not None:
                on_tool_result(name, content)
            self._conversation.add_tool_result(tool_call.id, content)

        return answer, bool(completion.tool_calls)
