from dataclasses import dataclass
from enum import StrEnum


class ConversationRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"


@dataclass(frozen=True, slots=True)
class ConversationTurn:
    turn_id: int
    role: ConversationRole
    transcript: str
    interrupted: bool = False
    tools: tuple[str, ...] = ()
