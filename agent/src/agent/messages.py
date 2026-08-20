from collections.abc import Sequence

from llmify import (
    AssistantMessage,
    Message,
    SystemMessage,
    ToolCall,
    ToolResultMessage,
    UserMessage,
)

from agent.prompt import SystemPrompt


class MessageManager:
    """Append-only conversation history sent to the model on each turn."""

    def __init__(
        self,
        system_prompt: SystemPrompt,
        messages: Sequence[Message] = (),
    ) -> None:
        self._system_prompt = system_prompt
        self._messages = list(messages)

    def add_user(self, text: str) -> None:
        self._messages.append(UserMessage(content=text))

    def add_assistant(self, text: str) -> None:
        self._messages.append(AssistantMessage(content=text))

    def add_tool_round(
        self,
        text: str,
        tool_calls: list[ToolCall],
        tool_results: list[ToolResultMessage],
    ) -> None:
        self._messages.append(AssistantMessage(content=text, tool_calls=tool_calls))
        self._messages.extend(tool_results)

    def to_llm_messages(self) -> list[Message]:
        return [SystemMessage(content=self._system_prompt.render()), *self._messages]
