from __future__ import annotations

from dataclasses import dataclass, field

from llmify import AssistantMessage, SystemMessage, UserMessage

type Message = SystemMessage | UserMessage | AssistantMessage


@dataclass
class Conversation:
    """Mutable conversation history for one voice session."""

    system_prompt: str
    messages: list[Message] = field(default_factory=list)
    max_turns: int = 12

    def add_user(self, text: str) -> None:
        self.messages.append(UserMessage(content=text))
        self.trim()

    def add_assistant(self, text: str) -> None:
        self.messages.append(AssistantMessage(content=text))
        self.trim()

    def to_llm_messages(self) -> list[Message]:
        self.trim()
        return [SystemMessage(content=self.system_prompt), *self.messages]

    def trim(self) -> None:
        max_messages = max(0, self.max_turns * 2)
        if max_messages and len(self.messages) > max_messages:
            self.messages[:] = self.messages[-max_messages:]
