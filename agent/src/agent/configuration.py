from pathlib import Path
from typing import Self
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from agent.clock import DEFAULT_TIMEZONE
from agent.sandbox import SandboxDefinition
from llm import CodexModel


class WorkspaceSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    root: Path | None = None
    max_file_bytes: int | None = Field(default=None, gt=0)


class AgentSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    models: tuple[CodexModel, ...] = Field(
        default=(CodexModel.SPARK,),
        min_length=1,
    )
    default_model: CodexModel = CodexModel.SPARK
    workspace: WorkspaceSettings = Field(default_factory=WorkspaceSettings)
    sandbox: SandboxDefinition | None = None
    system_prompt: str | None = None
    timezone: str = DEFAULT_TIMEZONE

    @field_validator("models")
    @classmethod
    def _models_must_be_unique(
        cls,
        models: tuple[CodexModel, ...],
    ) -> tuple[CodexModel, ...]:
        if len(set(models)) != len(models):
            raise ValueError("models must not contain duplicates")
        return models

    @field_validator("timezone")
    @classmethod
    def _timezone_must_be_resolvable(cls, timezone: str) -> str:
        try:
            ZoneInfo(timezone)
        except (KeyError, ValueError) as error:
            raise ValueError(f"Unknown timezone: {timezone!r}") from error
        return timezone

    @model_validator(mode="after")
    def _default_model_must_be_available(self) -> Self:
        if self.default_model not in self.models:
            raise ValueError("default_model must be included in models")
        return self
