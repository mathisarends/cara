import time

from pydantic import BaseModel, ConfigDict, Field

from voice.echo_cancellation.ports import Clock


class EchoCancellationSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    sample_rate: int | None = Field(default=None, gt=0)
    alignment_margin_s: float = Field(default=0.04, ge=0.0)
    history_seconds: float = Field(default=2.0, gt=0.0)
    clock: Clock = time.monotonic
