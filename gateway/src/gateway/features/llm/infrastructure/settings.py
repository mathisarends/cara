from typing import Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from llm import CodexModel


class LlmSettings(BaseModel):
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
