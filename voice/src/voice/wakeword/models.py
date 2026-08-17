from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict, Field
from wakewordkit import WakeWord


class WakeWordSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    wake_word: WakeWord = WakeWord.HEY_MYCROFT
    sensitivity: float = Field(default=0.5, ge=0.0, le=1.0)
    cooldown: float = Field(default=1.5, ge=0.0)


@dataclass(frozen=True, slots=True)
class WakeWordDetection:
    sequence: int
    score: float
    name: str
