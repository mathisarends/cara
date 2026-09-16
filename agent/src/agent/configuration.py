from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, field_validator

from agent.clock import DEFAULT_TIMEZONE


class AgentSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    system_prompt: str | None = None
    timezone: str = DEFAULT_TIMEZONE

    @field_validator("timezone")
    @classmethod
    def _timezone_must_be_resolvable(cls, timezone: str) -> str:
        try:
            ZoneInfo(timezone)
        except (KeyError, ValueError) as error:
            raise ValueError(f"Unknown timezone: {timezone!r}") from error
        return timezone
