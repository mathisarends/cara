from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class OpenAICredentials(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="OPENAI_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    api_key: SecretStr
