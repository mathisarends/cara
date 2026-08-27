from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field


class BargeInMode(StrEnum):
    SPEECH = "speech"
    WAKE_WORD = "wake_word"
    NONE = "none"


class _BargeInConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class SpeechBargeInConfig(_BargeInConfig):
    mode: Literal[BargeInMode.SPEECH]
    min_level_dbfs: float = Field(default=-45.0, le=0.0)
    min_speech_probability: float = Field(default=0.6, gt=0.0, le=1.0)
    min_speech_seconds: float = Field(default=0.35, gt=0.0)


class WakeWordBargeInConfig(_BargeInConfig):
    mode: Literal[BargeInMode.WAKE_WORD] = BargeInMode.WAKE_WORD


class NoBargeInConfig(_BargeInConfig):
    mode: Literal[BargeInMode.NONE]


BargeInConfig = Annotated[
    SpeechBargeInConfig | WakeWordBargeInConfig | NoBargeInConfig,
    Field(discriminator="mode"),
]
