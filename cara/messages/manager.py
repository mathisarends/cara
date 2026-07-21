from llmify import (
    AssistantMessage,
    Message,
    SystemMessage,
    ToolCall,
    ToolResultMessage,
    UserMessage,
)

from cara.messages.context import RuntimeContext
from cara.messages.system_prompt import SystemPrompt
from cara.skills import Skills


class MessageManager:
    def __init__(
        self,
        *,
        system_prompt: str | SystemPrompt | None = None,
        messages: list[Message] | None = None,
        max_turns: int = 12,
        skills: Skills | None = None,
        context: RuntimeContext | None = None,
    ) -> None:
        self._system_prompt = system_prompt if system_prompt is not None else SystemPrompt()
        self._messages = messages if messages is not None else []
        self._max_turns = max_turns
        self._skills = skills
        self._context = context

    def add_user(self, text: str) -> None:
        self._messages.append(UserMessage(content=text))
        self.trim()

    def add_assistant(self, text: str) -> None:
        self._messages.append(AssistantMessage(content=text))
        self.trim()

    def add_tool_results(self, results: list[tuple[ToolCall, str]]) -> None:
        if not results:
            return
        self._messages.append(AssistantMessage(tool_calls=[tool_call for tool_call, _ in results]))
        self._messages.extend(
            ToolResultMessage(tool_call_id=tool_call.id, content=content) for tool_call, content in results
        )
        self.trim()

    def to_llm_messages(self) -> list[Message]:
        self.trim()
        return [SystemMessage(content=self._render_system_prompt()), *self._messages]

    def trim(self) -> None:
        max_messages = max(0, self._max_turns * 2)
        if max_messages and len(self._messages) > max_messages:
            self._messages[:] = self._messages[-max_messages:]
        self._drop_orphan_tool_results()

    def _drop_orphan_tool_results(self) -> None:
        while self._messages and isinstance(self._messages[0], ToolResultMessage):
            self._messages.pop(0)

    def _render_system_prompt(self) -> str:
        base = self._system_prompt.render() if isinstance(self._system_prompt, SystemPrompt) else self._system_prompt
        sections = [base]
        if self._context is not None and (rendered := self._context.render()):
            sections.append(f"<context>\n{rendered}\n</context>")
        if self._skills is not None and (catalog := self._skills.render_catalog()):
            sections.append(f"<available_skills>\n{catalog}\n</available_skills>")
        return "\n\n".join(sections)
