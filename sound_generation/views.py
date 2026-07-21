from enum import StrEnum
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, field_validator


class SoundEffectModel(StrEnum):
    ELEVEN_TEXT_TO_SOUND_V2 = "eleven_text_to_sound_v2"


class SoundEffectFormat(StrEnum):
    MP3_22050_32 = "mp3_22050_32"
    MP3_44100_64 = "mp3_44100_64"
    MP3_44100_128 = "mp3_44100_128"
    MP3_44100_192 = "mp3_44100_192"
    PCM_16000 = "pcm_16000"
    PCM_24000 = "pcm_24000"
    PCM_44100 = "pcm_44100"


_CONTENT_TYPES = {
    SoundEffectFormat.MP3_22050_32: "audio/mpeg",
    SoundEffectFormat.MP3_44100_64: "audio/mpeg",
    SoundEffectFormat.MP3_44100_128: "audio/mpeg",
    SoundEffectFormat.MP3_44100_192: "audio/mpeg",
    SoundEffectFormat.PCM_16000: "audio/pcm",
    SoundEffectFormat.PCM_24000: "audio/pcm",
    SoundEffectFormat.PCM_44100: "audio/pcm",
}


def content_type_for(output_format: SoundEffectFormat) -> str:
    return _CONTENT_TYPES[output_format]


class SoundEffectRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=1000)
    model: SoundEffectModel = SoundEffectModel.ELEVEN_TEXT_TO_SOUND_V2
    output_format: SoundEffectFormat = SoundEffectFormat.MP3_44100_128
    duration_seconds: float | None = Field(default=None, ge=0.5, le=30.0)
    prompt_influence: float = Field(default=0.3, ge=0.0, le=1.0)
    loop: bool = False

    @field_validator("text")
    @classmethod
    def text_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("text must not be blank")
        return value


class SoundEffectResponse(BaseModel):
    audio: bytes = Field(repr=False)
    text: str
    model: SoundEffectModel
    output_format: SoundEffectFormat
    content_type: str

    @classmethod
    def from_request(cls, request: SoundEffectRequest, audio: bytes) -> Self:
        return cls(
            audio=audio,
            text=request.text,
            model=request.model,
            output_format=request.output_format,
            content_type=content_type_for(request.output_format),
        )
