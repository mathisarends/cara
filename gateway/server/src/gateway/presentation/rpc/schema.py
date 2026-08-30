from pydantic import BaseModel, ConfigDict


class WireSchema(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
