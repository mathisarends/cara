from enum import StrEnum
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class StreamingSpeechToTextModel(StrEnum):
    FLUX_GENERAL_EN = "flux-general-en"
    FLUX_GENERAL_MULTI = "flux-general-multi"


class StreamingSpeechToTextEncoding(StrEnum):
    LINEAR16 = "linear16"
    MULAW = "mulaw"
    ALAW = "alaw"


class StreamingSpeechToTextConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model: StreamingSpeechToTextModel | str = StreamingSpeechToTextModel.FLUX_GENERAL_EN
    encoding: StreamingSpeechToTextEncoding = StreamingSpeechToTextEncoding.LINEAR16
    sample_rate: int = Field(default=16000, gt=0)
    keyterms: list[str] | None = Field(default=None, serialization_alias="keyterm")
    eot_threshold: float | None = Field(default=None, ge=0.5, le=0.9)
    eager_eot_threshold: float | None = Field(default=None, ge=0.3, le=0.9)
    eot_timeout_ms: int | None = Field(default=None, ge=500, le=60000)

    @field_validator("keyterms")
    @classmethod
    def keyterms_must_not_be_blank(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        if any(not keyterm.strip() for keyterm in value):
            raise ValueError("keyterms must not contain blank values")
        return value

    @model_validator(mode="after")
    def eager_threshold_must_not_exceed_end_threshold(self) -> Self:
        eot = self.eot_threshold if self.eot_threshold is not None else 0.7
        if self.eager_eot_threshold is not None and self.eager_eot_threshold > eot:
            raise ValueError("eager_eot_threshold must not exceed eot_threshold")
        return self
