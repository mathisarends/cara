from pathlib import Path
from typing import Self

from pydantic import BaseModel, ConfigDict, Field
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    YamlConfigSettingsSource,
)

DEFAULT_CONFIG_FILE = Path("voice.yaml")


class GatewayConfig(BaseModel):
    # The Gateway shares the CARA_GATEWAY_* namespace in .env for its own settings.
    model_config = ConfigDict(extra="ignore", frozen=True)

    url: str = "http://127.0.0.1:8000"
    token: str = Field(min_length=1)


class SessionConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    channel: str = Field(default="voice", min_length=1)
    device_id: str = Field(default="default-voice-device", min_length=1)
    new_session: bool = False
    inactivity_timeout_seconds: float = Field(default=1800, gt=0)


class VoiceChannelConfig(BaseSettings):
    """Voice channel connection settings: YAML file, overridable by CARA_* env vars."""

    model_config = SettingsConfigDict(
        env_prefix="CARA_",
        env_nested_delimiter="_",
        env_nested_max_split=1,
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        frozen=True,
        yaml_file=(DEFAULT_CONFIG_FILE, "voice.yml"),
    )

    gateway: GatewayConfig
    voice: SessionConfig = Field(default_factory=SessionConfig)

    @classmethod
    def from_yaml(cls, path: str | Path = DEFAULT_CONFIG_FILE) -> Self:
        return cls(_yaml_file=path)

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return (
            init_settings,
            env_settings,
            dotenv_settings,
            YamlConfigSettingsSource(settings_cls),
            file_secret_settings,
        )
