from pathlib import Path

from pydantic import BaseModel, ConfigDict


class AgentResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    recording_path: Path | None
