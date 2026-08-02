from agenttoolkit import Skills
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


class MessageManager:
    def __init__(
        self,
        *,
        system_prompt: str | SystemPrompt | None = None,
        messages: list[Message] | None = None,
        skills: Skills | None = None,
        context: RuntimeContext | None = None,
    ) -> None:
        self._system_prompt = system_prompt if system_prompt is not None else SystemPrompt()
        self._messages = messages if messages is not None else []
        self._skills = skills
        self._context = context

    def add_user(self, text: str) -> None:
        self._messages.append(UserMessage(content=text))

    def add_assistant(self, text: str) -> None:
        self._messages.append(AssistantMessage(content=text))

    def add_tool_call(self, tool_call: ToolCall) -> None:
        self._messages.append(AssistantMessage(tool_calls=[tool_call]))

    def add_tool_result(self, tool_call_id: str, content: str) -> None:
        self._messages.append(ToolResultMessage(tool_call_id=tool_call_id, content=content))

    def to_llm_messages(self) -> list[Message]:
        return [SystemMessage(content=self._render_system_prompt()), *self._messages]

    def _render_system_prompt(self) -> str:
        base = self._system_prompt.render() if isinstance(self._system_prompt, SystemPrompt) else self._system_prompt
        sections = [base]
        if self._context is not None and (rendered := self._context.render()):
            sections.append(f"<context>\n{rendered}\n</context>")
        if self._skills is not None and (catalog := self._skills.render_prompt()):
            sections.append(catalog)
        return "\n\n".join(sections)
