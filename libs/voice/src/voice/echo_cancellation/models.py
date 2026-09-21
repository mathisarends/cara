from pydantic import BaseModel, ConfigDict, Field


class ReferenceAlignmentSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    window_seconds: float = Field(default=0.16, gt=0.0)
    interval_seconds: float = Field(default=0.08, gt=0.0)
    tracking_seconds: float = Field(default=0.06, ge=0.0)
    filter_headroom_seconds: float = Field(default=0.02, ge=0.0)
    min_correlation: float = Field(default=0.5, gt=0.0, le=1.0)
    min_level_dbfs: float = Field(default=-50.0, le=0.0)
    analysis_sample_rate: int = Field(default=8_000, gt=0)


class EchoCancellationSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    sample_rate: int | None = Field(default=None, gt=0)
    reference_history_seconds: float = Field(default=8.0, gt=0.0)
    max_upload_echo_confidence: float = Field(default=0.5, gt=0.0, le=1.0)
    alignment: ReferenceAlignmentSettings = Field(
        default_factory=ReferenceAlignmentSettings
    )
