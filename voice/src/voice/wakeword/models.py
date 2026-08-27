from dataclasses import dataclass
from typing import Annotated

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field
from wakewordkit import WakeWord


def _resolve_wake_word(value: object) -> object:
    if isinstance(value, str):
        return WakeWord.__members__.get(value.upper(), value)
    return value


# Accepts the readable member name, e.g. "hey_jarvis" for "hey_jarvis_v0.1".
_ConfiguredWakeWord = Annotated[WakeWord, BeforeValidator(_resolve_wake_word)]


class WakeWordSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    wake_word: _ConfiguredWakeWord = WakeWord.HEY_MYCROFT
    sensitivity: float = Field(default=0.5, ge=0.0, le=1.0)
    cooldown: float = Field(default=1.5, ge=0.0)
    strip_from_command: bool = True


@dataclass(frozen=True, slots=True)
class WakeWordDetection:
    sequence: int
    score: float
    name: str
