import json
from collections.abc import Callable

from agenttoolkit import Skills, Tools
from llmify import ChatInvokeCompletion, ChatModel

from cara.prompt import Conversation, SystemPromptComposer


class Agent:
    def __init__(
        self,
        *,
        llm: ChatModel,
        tools: Tools,
        skills: Skills | None = None,
        system_prompt: str | None = None,
        override_system_prompt: str | None = None,
        extend_system_prompt: str | None = None,
    ) -> None:
        self._llm = llm
        self._tools = tools
        self._conversation = Conversation(
            system_prompt=SystemPromptComposer(
                system_prompt=system_prompt,
                override_system_prompt=override_system_prompt,
                extend_system_prompt=extend_system_prompt,
                skills=skills,
            ),
        )

    async def respond(
        self,
        text: str,
        *,
        on_tool_call: Callable[[str, dict[str, object]], None] | None = None,
        on_tool_result: Callable[[str, str, bool], None] | None = None,
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
        on_tool_result: Callable[[str, str, bool], None] | None,
    ) -> str:
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

    async def _resolve_completion(
        self,
        completion: ChatInvokeCompletion[str],
        *,
        on_tool_call: Callable[[str, dict[str, object]], None] | None,
        on_tool_result: Callable[[str, str, bool], None] | None,
    ) -> tuple[str, bool]:
        answer = completion.completion.strip()
        for tool_call in completion.tool_calls:
            self._conversation.add_tool_call(tool_call)
            name = tool_call.function.name
            arguments = json.loads(tool_call.function.arguments or "{}")
            if on_tool_call is not None:
                on_tool_call(name, arguments)

            result = await self._tools.execute(name, arguments)
            fallback = "Tool completed successfully." if result.ok else "Tool failed."
            content = str(result.result or result.error or fallback)
            if on_tool_result is not None:
                on_tool_result(name, content, result.ok)
            self._conversation.add_tool_result(tool_call.id, content)

        return answer, bool(completion.tool_calls)
