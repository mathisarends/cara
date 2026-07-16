from pydantic import BaseModel, ConfigDict, Field


class EndSessionParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    farewell: str = Field(
        description="A short, friendly spoken goodbye in the user's language.",
    )
