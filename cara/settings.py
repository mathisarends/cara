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

    api_key: SecretStr | None = None

    def require_api_key(self) -> str:
        if self.api_key is None:
            raise RuntimeError(
                "OPENAI_API_KEY is not set. Add it to your environment or to the project's .env file."
            )
        return self.api_key.get_secret_value()
