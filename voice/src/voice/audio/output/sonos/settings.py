from pydantic_settings import BaseSettings, SettingsConfigDict


class SonosSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="SONOS_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    speaker_name: str | None = None
    ip_address: str | None = None
    local_host: str | None = None
