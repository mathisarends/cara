from llmify import AssistantMessage, Message, SystemMessage, UserMessage

from cara.messages.system_prompt import SystemPrompt


class MessageManager:
    def __init__(
        self,
        *,
        system_prompt: str | SystemPrompt | None = None,
        messages: list[Message] | None = None,
        max_turns: int = 12,
    ) -> None:
        self._system_prompt = system_prompt if system_prompt is not None else SystemPrompt()
        self._messages = messages if messages is not None else []
        self._max_turns = max_turns

    def add_user(self, text: str) -> None:
        self._messages.append(UserMessage(content=text))
        self.trim()

    def add_assistant(self, text: str) -> None:
        self._messages.append(AssistantMessage(content=text))
        self.trim()

    def to_llm_messages(self) -> list[Message]:
        self.trim()
        return [SystemMessage(content=self._render_system_prompt()), *self._messages]

    def trim(self) -> None:
        max_messages = max(0, self._max_turns * 2)
        if max_messages and len(self._messages) > max_messages:
            self._messages[:] = self._messages[-max_messages:]

    def _render_system_prompt(self) -> str:
        if isinstance(self._system_prompt, SystemPrompt):
            return self._system_prompt.render()
        return self._system_prompt
