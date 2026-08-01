import json

from agenttoolkit import Skills
from llmify import ChatInvokeCompletion, ChatModel, ToolCall

from cara.messages import MessageManager, SystemPrompt
from cara.tools import Tools


class Agent:
    """Runs one text conversation independently of its input and output channel."""

    def __init__(
        self,
        *,
        llm: ChatModel,
        tools: Tools,
        skills: Skills | None = None,
        system_prompt: str | SystemPrompt | None = None,
        override_system_prompt: str | None = None,
        extend_system_prompt: str | None = None,
    ) -> None:
        self._llm = llm
        self._tools = tools
        self._message_manager = MessageManager(
            system_prompt=_build_system_prompt(
                system_prompt=system_prompt,
                override_system_prompt=override_system_prompt,
                extend_system_prompt=extend_system_prompt,
            ),
            skills=skills,
        )

    async def respond(self, text: str) -> str:
        """Add a user turn, run the model and tools, and return the final answer."""
        text = text.strip()
        if not text:
            return ""

        self._message_manager.add_user(text)
        answer = await self._generate_answer()
        self._message_manager.add_assistant(answer)
        return answer

    async def _generate_answer(self) -> str:
        while True:
            completion = await self._llm.invoke(
                self._message_manager.to_llm_messages(),
                tools=self._tools.get_schema("openai"),
            )
            answer, called_tools = await self._resolve_completion(completion)
            if not called_tools:
                return answer

    async def _resolve_completion(
        self,
        completion: ChatInvokeCompletion[str],
    ) -> tuple[str, bool]:
        answer = completion.completion.strip()
        tool_results: list[tuple[ToolCall, str]] = []
        for tool_call in completion.tool_calls:
            name = tool_call.function.name
            arguments = json.loads(tool_call.function.arguments or "{}")

            result = await self._tools.execute(name, arguments)
            fallback = "Tool completed successfully." if result.ok else "Tool failed."
            content = str(result.result or result.error or fallback)
            tool_results.append((tool_call, content))

        self._message_manager.add_tool_results(tool_results)
        return answer, bool(completion.tool_calls)


def _build_system_prompt(
    *,
    system_prompt: str | SystemPrompt | None,
    override_system_prompt: str | None,
    extend_system_prompt: str | None,
) -> str | SystemPrompt:
    if system_prompt is not None and (override_system_prompt is not None or extend_system_prompt is not None):
        raise ValueError("Use system_prompt or override_system_prompt/extend_system_prompt, not both.")
    if system_prompt is not None:
        return system_prompt
    return SystemPrompt(
        override_system_prompt=override_system_prompt,
        extend_system_prompt=extend_system_prompt,
    )
