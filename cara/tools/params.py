from pydantic import BaseModel, ConfigDict, Field


class ToolParams(BaseModel):
    """Base class for tool parameter models.

    Every tool call carries a ``status``: a short spoken announcement the LLM
    phrases per call, played while the tool executes.
    """

    model_config = ConfigDict(extra="forbid")

    status: str = Field(
        description=(
            "A short spoken status announcement in the user's language, phrased "
            "as if said aloud while the tool runs, e.g. 'Ich schaue kurz in "
            "deinen Kalender...'"
        ),
    )


class EndSessionParams(ToolParams):
    farewell: str = Field(
        description="A short, friendly spoken goodbye in the user's language.",
    )


class LoadSkillParams(ToolParams):
    name: str = Field(description="Name of the skill to load, exactly as listed.")
