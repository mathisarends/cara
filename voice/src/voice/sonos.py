from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class SonosSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="SONOS_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    ip_address: str
    local_host: str | None = None
    # Speech carries less energy than music, so clips play above the speaker's
    # own volume rather than at it.
    clip_volume_boost: int = Field(default=15, ge=0, le=100)
    # Start with enough synthesized audio to absorb TTS and network jitter
    # without adding noticeable latency before Sonos fetches the stream.
    clip_prebuffer_seconds: float = Field(default=0.25, ge=0.0)
