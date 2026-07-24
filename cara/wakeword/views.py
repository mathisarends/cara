from pydantic import BaseModel, ConfigDict, Field
from wakewordkit import WakeWord


class WakeWordSettings(BaseModel):
    """Wake word detection settings for the assistant."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    wake_word: WakeWord = WakeWord.HEY_MYCROFT
    sensitivity: float = Field(default=0.5, ge=0.0, le=1.0)
