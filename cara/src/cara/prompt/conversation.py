from llmify import (
    AssistantMessage,
    Message,
    SystemMessage,
    ToolCall,
    ToolResultMessage,
    UserMessage,
)

from cara.prompt.composer import SystemPromptComposer


class Conversation:
    """The ordered message history sent to the model on each turn."""

    def __init__(
        self,
        *,
        system_prompt: SystemPromptComposer,
        messages: list[Message] | None = None,
    ) -> None:
        self._system_prompt = system_prompt
        self._history = messages if messages is not None else []

    def add_user(self, text: str) -> None:
        self._history.append(UserMessage(content=text))

    def add_assistant(self, text: str) -> None:
        self._history.append(AssistantMessage(content=text))

    def add_tool_call(self, tool_call: ToolCall) -> None:
        self._history.append(AssistantMessage(tool_calls=[tool_call]))

    def add_tool_result(self, tool_call_id: str, content: str) -> None:
        self._history.append(
            ToolResultMessage(tool_call_id=tool_call_id, content=content)
        )

    def to_llm_messages(self) -> list[Message]:
        return [SystemMessage(content=self._system_prompt.render()), *self._history]

    def to_current_turn_messages(self) -> list[Message]:
        """Return the current instructions and the latest user turn only."""
        for message in reversed(self._history):
            if isinstance(message, UserMessage):
                return [SystemMessage(content=self._system_prompt.render()), message]
        raise RuntimeError("The conversation does not contain a user turn.")
