from pathlib import Path

from pydantic_settings import SettingsConfigDict

from sandbox_manager.settings import SandboxManagerYamlSettings


class FilesSettings(SandboxManagerYamlSettings):
    model_config = SettingsConfigDict(
        yaml_config_section="sandbox_manager",
    )

    workspace_root: Path = Path("/workspace")
