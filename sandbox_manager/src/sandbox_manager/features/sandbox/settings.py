import os
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import SettingsConfigDict

from sandbox_manager.settings import SandboxManagerYamlSettings


class SandboxSettings(SandboxManagerYamlSettings):
    model_config = SettingsConfigDict(
        yaml_config_section="sandbox_manager",
    )

    image: str = "cara-bash-sandbox:latest"
    workspace_volume: str = "cara-workspace"
    cli_config_volume: str = "cara-cli-config"
    # Each host directory is bind-mounted read-write at /tmp/.config/<name>,
    # shadowing that slice of cli_config_volume for CLIs with an existing host config.
    cli_credential_mounts: dict[str, Path] = Field(default_factory=dict)
    idle_ttl_seconds: float = Field(default=600, gt=0)
    reap_interval_seconds: float = Field(default=10, gt=0)
    memory_bytes: int = Field(default=536_870_912, gt=0)
    pids: int = Field(default=512, gt=0)
    cpus: float = Field(default=1, gt=0)
    network_access: bool = True
    max_output_bytes: int = Field(default=1_000_000, gt=0)

    @field_validator("cli_credential_mounts", mode="before")
    @classmethod
    def expand_credential_paths(cls, value: object) -> object:
        if not isinstance(value, dict):
            return value
        return {name: os.path.expandvars(str(path)) for name, path in value.items()}
