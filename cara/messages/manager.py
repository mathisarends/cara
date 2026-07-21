from collections.abc import Callable

from llmify import AssistantMessage, Message, SystemMessage, UserMessage

from cara.messages.system_prompt import SystemPrompt


class MessageManager:
    def __init__(
        self,
        *,
        system_prompt: str | SystemPrompt | None = None,
        messages: list[Message] | None = None,
        max_turns: int = 12,
        context_provider: Callable[[], str] | None = None,
    ) -> None:
        self._system_prompt = system_prompt if system_prompt is not None else SystemPrompt()
        self._messages = messages if messages is not None else []
        self._max_turns = max_turns
        self._context_provider = context_provider

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
        base = self._system_prompt.render() if isinstance(self._system_prompt, SystemPrompt) else self._system_prompt
        if self._context_provider is None:
            return base
        extra = self._context_provider().strip()
        return f"{base}\n\n{extra}" if extra else base
