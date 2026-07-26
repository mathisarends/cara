import json

from llmify import ChatModel, ChatOpenAI, ToolCall

from cara.llm import LanguageModels
from cara.messages import MessageManager, SystemPrompt
from cara.skills import Skills
from cara.tools import Tools

_DEFAULT_SYSTEM_PROMPT = (
    "You are Cara, a concise text-based assistant. Answer the user directly "
    "and use the available tools when they help complete the request."
)
_DEFAULT_MAX_TOOL_ROUNDS = 20


class Subagent:
    """A minimal text-in, text-out agent with iterative tool use."""

    def __init__(
        self,
        *,
        llm: ChatModel | None = None,
        models: LanguageModels | None = None,
        api_key: str | None = None,
        tools: Tools | None = None,
        skills: Skills | None = None,
        system_prompt: str | SystemPrompt = _DEFAULT_SYSTEM_PROMPT,
        max_tool_rounds: int = _DEFAULT_MAX_TOOL_ROUNDS,
    ) -> None:
        if models is not None and llm is not None:
            raise ValueError("Use models or llm, not both.")
        if max_tool_rounds < 1:
            raise ValueError("max_tool_rounds must be positive.")

        self._models = models or LanguageModels.single(
            llm or ChatOpenAI(model="gpt-5.6-terra", api_key=api_key, reasoning_effort="none")
        )
        self._tools = tools or Tools()
        self._tools.provide(self._models)
        if skills is not None:
            self._tools.provide(skills)
        self._messages = MessageManager(
            system_prompt=system_prompt,
            skills=skills,
        )
        self._max_tool_rounds = max_tool_rounds

    async def run(self, prompt: str) -> str:
        """Run one conversational turn and return the final text response."""
        self._messages.add_user(prompt)

        for _ in range(self._max_tool_rounds):
            completion = await self._models.current().invoke(
                self._messages.to_llm_messages(),
                tools=self._tools.to_schema(),
            )
            if not completion.tool_calls:
                answer = completion.completion.strip()
                self._messages.add_assistant(answer)
                return answer

            self._messages.add_tool_results(await self._execute(completion.tool_calls))

        raise RuntimeError(f"Subagent exceeded {self._max_tool_rounds} consecutive tool rounds.")

    async def _execute(self, tool_calls: list[ToolCall]) -> list[tuple[ToolCall, str]]:
        results = []
        for tool_call in tool_calls:
            arguments = json.loads(tool_call.function.arguments or "{}")
            if not isinstance(arguments, dict):
                raise ValueError(f"Tool arguments for {tool_call.function.name!r} must be a JSON object.")

            result = await self._tools.execute(tool_call.function.name, arguments)
            content = result.content or ("Tool completed successfully." if result.ok else "Tool failed.")
            results.append((tool_call, content))
        return results


__all__ = ["Subagent"]
