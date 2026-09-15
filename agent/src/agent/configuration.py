from typing import Self
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from agent.clock import DEFAULT_TIMEZONE
from llm import CodexModel


class ModelSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    default: CodexModel = CodexModel.SPARK
    available: tuple[CodexModel, ...] = Field(
        default=(CodexModel.SPARK,),
        min_length=1,
    )

    @field_validator("available")
    @classmethod
    def _models_must_be_unique(
        cls,
        models: tuple[CodexModel, ...],
    ) -> tuple[CodexModel, ...]:
        if len(set(models)) != len(models):
            raise ValueError("models must not contain duplicates")
        return models

    @model_validator(mode="after")
    def _default_model_must_be_available(self) -> Self:
        if self.default not in self.available:
            raise ValueError("default model must be included in available models")
        return self


class AgentSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    models: ModelSettings = Field(default_factory=ModelSettings)
    system_prompt: str | None = None
    timezone: str = DEFAULT_TIMEZONE

    @field_validator("timezone")
    @classmethod
    def _timezone_must_be_resolvable(cls, timezone: str) -> str:
        try:
            ZoneInfo(timezone)
        except (KeyError, ValueError) as error:
            raise ValueError(f"Unknown timezone: {timezone!r}") from error
        return timezone
