from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class SandboxManagerSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="CARA_SANDBOX_",
        env_file=".env",
        extra="ignore",
    )

    image: str = "cara-bash-sandbox:latest"
    workspace_volume: str = "cara-workspace"
    cli_config_volume: str = "cara-cli-config"
    workspace_root: Path = Path("/workspace")
    idle_ttl_seconds: float = Field(default=600, gt=0)
    reap_interval_seconds: float = Field(default=10, gt=0)
    memory_bytes: int = Field(default=536_870_912, gt=0)
    pids: int = Field(default=512, gt=0)
    cpus: float = Field(default=1, gt=0)
    network_access: bool = True
    max_output_bytes: int = Field(default=1_000_000, gt=0)
    token: SecretStr
