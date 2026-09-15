from pathlib import Path

from sandbox_manager.features.files.settings import FilesSettings
from sandbox_manager.features.sandbox.settings import SandboxSettings
from sandbox_manager.presentation.authentication import AuthSettings


def test_settings_are_loaded_from_gateway_yaml(
    tmp_path: Path,
    monkeypatch,
) -> None:
    config = tmp_path / "gateway.yaml"
    config.write_text(
        """
sandbox:
  token: shared-token
sandbox_manager:
  workspace_root: /workspace
  image: custom-sandbox:latest
  idle_ttl_seconds: 120
  cli_credential_mounts:
    spoti: ${APPDATA}/spoti
""".strip(),
        encoding="utf-8",
    )
    monkeypatch.setenv("APPDATA", "C:/Users/example/AppData/Roaming")
    monkeypatch.chdir(tmp_path)

    sandbox = SandboxSettings()
    files = FilesSettings()
    auth = AuthSettings()

    assert sandbox.image == "custom-sandbox:latest"
    assert sandbox.idle_ttl_seconds == 120
    assert sandbox.cli_credential_mounts == {
        "spoti": Path("C:/Users/example/AppData/Roaming/spoti")
    }
    assert files.workspace_root == Path("/workspace")
    assert auth.token.get_secret_value() == "shared-token"
