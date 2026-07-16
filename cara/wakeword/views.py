from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class WakeWord(StrEnum):
    ALEXA = "alexa"
    HEY_MYCROFT = "hey mycroft"
    HEY_RHASSPY = "hey rhasspy"


WAKE_WORD_MODEL: dict[WakeWord, str] = {
    WakeWord.ALEXA: "alexa",
    WakeWord.HEY_MYCROFT: "hey_mycroft",
    WakeWord.HEY_RHASSPY: "hey_rhasspy",
}


class WakeWordSettings(BaseModel):
    """Wake word detection settings for the assistant."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    wake_word: WakeWord = WakeWord.HEY_MYCROFT
    sensitivity: float = Field(default=0.5, ge=0.0, le=1.0)
