from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class StorageSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="CARA_GATEWAY_STORAGE_",
        extra="ignore",
        frozen=True,
    )

    bucket: str = "cara"
    endpoint_url: str | None = None
    public_endpoint_url: str | None = None
    access_key: str | None = None
    secret_key: SecretStr | None = None
