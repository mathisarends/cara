from pydantic import BaseModel, ConfigDict


class ToolParams(BaseModel):
    """Base class for tool parameter models."""

    model_config = ConfigDict(extra="forbid")
