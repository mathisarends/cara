from pathlib import Path

from pydantic import BaseModel, ConfigDict

from voice.conversation import ConversationMessage


class AgentResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    recording_path: Path | None
    conversation_history: tuple[ConversationMessage, ...]
