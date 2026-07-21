from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class OpenAICredentials(BaseSettings):
    """OpenAI credentials loaded from the environment and a local .env file."""

    model_config = SettingsConfigDict(
        env_prefix="OPENAI_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    api_key: SecretStr


class TavilyCredentials(BaseSettings):
    """Tavily credentials loaded from the environment and a local .env file."""

    model_config = SettingsConfigDict(
        env_prefix="TAVILY_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    api_key: SecretStr
