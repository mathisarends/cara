from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    YamlConfigSettingsSource,
)

from agent.configuration import AgentSettings
from gateway.agent_runtime.mcp import McpServerSettings
from gateway.agent_runtime.sandbox import SandboxClientSettings


class WorkspaceSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    root: Path | None = None


class GatewaySettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="CARA_",
        env_nested_delimiter="_",
        env_nested_max_split=1,
        extra="ignore",
        yaml_file=("gateway.yml", "gateway.yaml"),
    )

    agent: AgentSettings = Field(default_factory=AgentSettings)
    workspace: WorkspaceSettings = Field(default_factory=WorkspaceSettings)
    sandbox: SandboxClientSettings = Field(default_factory=SandboxClientSettings)
    tools: tuple[McpServerSettings, ...] = ()

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
