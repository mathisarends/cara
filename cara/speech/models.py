from enum import StrEnum
from pathlib import Path
from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class SpeechToTextModel(StrEnum):
    GPT_4O_TRANSCRIBE = "gpt-4o-transcribe"
    GPT_4O_MINI_TRANSCRIBE = "gpt-4o-mini-transcribe"
    GPT_4O_TRANSCRIBE_DIARIZE = "gpt-4o-transcribe-diarize"
    WHISPER_1 = "whisper-1"


class SpeechToTextFormat(StrEnum):
    JSON = "json"
    TEXT = "text"
    SRT = "srt"
    VERBOSE_JSON = "verbose_json"
    VTT = "vtt"
    DIARIZED_JSON = "diarized_json"


class TimestampGranularity(StrEnum):
    WORD = "word"
    SEGMENT = "segment"


class TextToSpeechModel(StrEnum):
    GPT_4O_MINI_TTS = "gpt-4o-mini-tts"
    TTS_1 = "tts-1"
    TTS_1_HD = "tts-1-hd"


class TextToSpeechVoice(StrEnum):
    ALLOY = "alloy"
    ASH = "ash"
    BALLAD = "ballad"
    CORAL = "coral"
    ECHO = "echo"
    FABLE = "fable"
    NOVA = "nova"
    ONYX = "onyx"
    SAGE = "sage"
    SHIMMER = "shimmer"
    VERSE = "verse"
    MARIN = "marin"
    CEDAR = "cedar"


class TextToSpeechFormat(StrEnum):
    MP3 = "mp3"
    OPUS = "opus"
    AAC = "aac"
    FLAC = "flac"
    WAV = "wav"
    PCM = "pcm"


class SpeechToTextRequest(BaseModel):
    """Validated request for OpenAI audio transcription."""

    model_config = ConfigDict(extra="forbid")

    audio_path: Path | None = None
    audio: bytes | None = Field(default=None, repr=False)
    filename: str = "utterance.wav"
    model: SpeechToTextModel = SpeechToTextModel.GPT_4O_TRANSCRIBE
    response_format: SpeechToTextFormat = SpeechToTextFormat.JSON
    language: str | None = Field(
        default=None,
        description="Optional ISO-639-1 language code such as 'de' or 'en'.",
    )
    prompt: str | None = None
    temperature: float | None = Field(default=None, ge=0, le=1)
    timestamp_granularities: list[TimestampGranularity] | None = None
    include: list[Literal["logprobs"]] | None = None
    chunking_strategy: Literal["auto"] | dict[str, Any] | None = None
    extra_body: dict[str, Any] | None = None

    @field_validator("audio_path")
    @classmethod
    def audio_path_must_exist(cls, value: Path | None) -> Path | None:
        if value is None:
            return value
        if not value.exists():
            raise ValueError(f"Audio file does not exist: {value}")
        if not value.is_file():
            raise ValueError(f"Audio path is not a file: {value}")
        return value

    @field_validator("language")
    @classmethod
    def language_must_be_iso_639_1(cls, value: str | None) -> str | None:
        if value is None:
            return value
        normalized = value.strip().lower()
        if len(normalized) != 2 or not normalized.isalpha():
            raise ValueError("language must be an ISO-639-1 code like 'de' or 'en'")
        return normalized

    @model_validator(mode="after")
    def exactly_one_audio_source(self) -> Self:
        if (self.audio_path is None) == (self.audio is None):
            raise ValueError("Provide exactly one of 'audio_path' or 'audio'.")
        return self

    @model_validator(mode="after")
    def validate_model_capabilities(self) -> Self:
        if self.model in {SpeechToTextModel.GPT_4O_TRANSCRIBE, SpeechToTextModel.GPT_4O_MINI_TRANSCRIBE}:
            supported = {SpeechToTextFormat.JSON, SpeechToTextFormat.TEXT}
            if self.response_format not in supported:
                raise ValueError(f"{self.model} supports only response_format json or text")

        if self.model == SpeechToTextModel.GPT_4O_TRANSCRIBE_DIARIZE:
            supported = {SpeechToTextFormat.JSON, SpeechToTextFormat.TEXT, SpeechToTextFormat.DIARIZED_JSON}
            if self.response_format not in supported:
                raise ValueError(f"{self.model} supports only response_format json, text, or diarized_json")
            if self.prompt is not None:
                raise ValueError(f"{self.model} does not support prompt")
            if self.include is not None:
                raise ValueError(f"{self.model} does not support include/logprobs")
            if self.timestamp_granularities is not None:
                raise ValueError(f"{self.model} does not support timestamp_granularities")

        if self.model == SpeechToTextModel.WHISPER_1:
            supported = {
                SpeechToTextFormat.JSON,
                SpeechToTextFormat.TEXT,
                SpeechToTextFormat.SRT,
                SpeechToTextFormat.VERBOSE_JSON,
                SpeechToTextFormat.VTT,
            }
            if self.response_format not in supported:
                raise ValueError(f"{self.model} supports only response_format json, text, srt, verbose_json, or vtt")

        if self.timestamp_granularities is not None and self.response_format != SpeechToTextFormat.VERBOSE_JSON:
            raise ValueError("timestamp_granularities requires response_format='verbose_json'")

        return self

    def to_openai_params(self) -> dict[str, Any]:
        params = self.model_dump(
            exclude={"audio_path", "audio", "filename"},
            exclude_none=True,
            mode="python",
        )
        if self.timestamp_granularities is not None:
            params["timestamp_granularities"] = self.timestamp_granularities
        return params


class SpeechToTextResponse(BaseModel):
    """Normalized transcription result."""

    model_config = ConfigDict(extra="allow")

    text: str
    model: SpeechToTextModel
    response_format: SpeechToTextFormat
    raw: dict[str, Any] | str


class TextToSpeechRequest(BaseModel):
    """Validated request for OpenAI speech generation."""

    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=4096)
    model: TextToSpeechModel = TextToSpeechModel.GPT_4O_MINI_TTS
    voice: TextToSpeechVoice = TextToSpeechVoice.MARIN
    response_format: TextToSpeechFormat = TextToSpeechFormat.MP3
    instructions: str | None = None
    speed: float | None = Field(default=None, ge=0.25, le=4.0)

    @field_validator("text")
    @classmethod
    def text_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("text must not be blank")
        return value

    @model_validator(mode="after")
    def validate_model_capabilities(self) -> Self:
        legacy_voices = {
            TextToSpeechVoice.ALLOY,
            TextToSpeechVoice.ASH,
            TextToSpeechVoice.CORAL,
            TextToSpeechVoice.ECHO,
            TextToSpeechVoice.FABLE,
            TextToSpeechVoice.ONYX,
            TextToSpeechVoice.NOVA,
            TextToSpeechVoice.SAGE,
            TextToSpeechVoice.SHIMMER,
        }
        if self.model in {TextToSpeechModel.TTS_1, TextToSpeechModel.TTS_1_HD} and self.voice not in legacy_voices:
            raise ValueError(f"{self.model} does not support voice '{self.voice}'")
        return self

class TextToSpeechResponse(BaseModel):
    """Generated speech audio bytes plus request metadata."""

    audio: bytes
    model: TextToSpeechModel
    voice: TextToSpeechVoice
    response_format: TextToSpeechFormat
    content_type: str
