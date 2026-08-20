from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    YamlConfigSettingsSource,
)


class AgentPluginSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    plugin: str = Field(default="echo", min_length=1)
    config: dict[str, Any] = Field(default_factory=dict)


class GatewaySettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="CARA_",
        env_nested_delimiter="_",
        env_nested_max_split=1,
        extra="ignore",
        yaml_file=("gateway.yaml", "gateway.yml"),
    )

    agent: AgentPluginSettings = Field(default_factory=AgentPluginSettings)

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
