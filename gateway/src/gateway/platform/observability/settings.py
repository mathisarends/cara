from pydantic_settings import BaseSettings, SettingsConfigDict


class TelemetrySettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="CARA_TELEMETRY_",
        extra="ignore",
        frozen=True,
    )

    enabled: bool = False
    service_name: str = "cara-gateway"
    otlp_endpoint: str = "http://localhost:4317"
    sample_ratio: float = 1.0
