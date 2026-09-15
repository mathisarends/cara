from pathlib import Path

from gateway.agent_runtime.workspace import resolve_workspace_root


def test_configured_workspace_root_is_resolved(tmp_path: Path) -> None:
    root = tmp_path / "configured"

    assert resolve_workspace_root(root) == root.resolve()


def test_environment_workspace_root_overrides_configuration(
    tmp_path: Path, monkeypatch
) -> None:
    configured = tmp_path / "configured"
    environment = tmp_path / "environment"
    monkeypatch.setenv("CARA_WORKSPACE_ROOT", str(environment))

    assert resolve_workspace_root(configured) == environment.resolve()
