from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field


class ConversationRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"


class ConversationTurn(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    turn_id: int
    role: ConversationRole
    transcript: str


class HumanMessage(ConversationTurn):
    role: Literal[ConversationRole.USER] = ConversationRole.USER


class AssistantMessage(ConversationTurn):
    role: Literal[ConversationRole.ASSISTANT] = ConversationRole.ASSISTANT


type ConversationMessage = Annotated[
    HumanMessage | AssistantMessage,
    Field(discriminator="role"),
]
