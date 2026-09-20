from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Credentials(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="DEEPGRAM_", env_file=".env", extra="ignore"
    )

    api_key: SecretStr = Field(min_length=1)
