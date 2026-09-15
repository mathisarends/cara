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
    # "<name>=<host dir>" pairs separated by ";" (not JSON: host paths on Windows
    # contain backslashes, which JSON would reject as invalid escapes). Each is
    # bind-mounted read-write at /tmp/.config/<name>, shadowing that slice of
    # cli_config_volume for CLIs with an existing host config. See credential_mounts().
    cli_credential_mounts: str = ""
    workspace_root: Path = Path("/workspace")
    idle_ttl_seconds: float = Field(default=600, gt=0)
    reap_interval_seconds: float = Field(default=10, gt=0)
    memory_bytes: int = Field(default=536_870_912, gt=0)
    pids: int = Field(default=512, gt=0)
    cpus: float = Field(default=1, gt=0)
    network_access: bool = True
    max_output_bytes: int = Field(default=1_000_000, gt=0)
    token: SecretStr

    def credential_mounts(self) -> dict[str, Path]:
        return _parse_credential_mounts(self.cli_credential_mounts)


def _parse_credential_mounts(raw: str) -> dict[str, Path]:
    pairs = (entry.split("=", 1) for entry in raw.split(";") if entry)
    return {name: Path(host_dir) for name, host_dir in pairs}
