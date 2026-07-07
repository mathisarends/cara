from pydantic import BaseModel, ConfigDict


class DoneParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
