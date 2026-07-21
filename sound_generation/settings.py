from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class ElevenLabsCredentials(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="ELEVENLABS_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    api_key: SecretStr
