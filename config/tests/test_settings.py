from pathlib import Path

import pytest
from pydantic import ValidationError

from config import CaraPaths, DockerBind, load_cara_config


def test_paths_have_home_directory_defaults(monkeypatch) -> None:
    monkeypatch.delenv("CARA_STATE_ROOT", raising=False)
    monkeypatch.delenv("CARA_WORKSPACE_ROOT", raising=False)

    paths = CaraPaths(_env_file=None)

    assert paths.state_root == Path.home() / ".cara"
    assert paths.workspace_root == Path.home() / ".cara" / "workspace"


def test_paths_are_configurable_through_environment(
    monkeypatch,
    tmp_path: Path,
) -> None:
    state_root = tmp_path / "state"
    workspace_root = tmp_path / "prompts"
    monkeypatch.setenv("CARA_STATE_ROOT", str(state_root))
    monkeypatch.setenv("CARA_WORKSPACE_ROOT", str(workspace_root))

    paths = CaraPaths(_env_file=None)

    assert paths.state_root == state_root
    assert paths.workspace_root == workspace_root


def test_environment_paths_expand_the_home_directory(monkeypatch) -> None:
    monkeypatch.setenv("CARA_WORKSPACE_ROOT", "~/cara-prompts")

    paths = CaraPaths(_env_file=None)

    assert paths.workspace_root == Path.home() / "cara-prompts"


def test_loads_json5_workspace_and_docker_binds(tmp_path: Path) -> None:
    state_root = tmp_path / "state"
    state_root.mkdir()
    (state_root / "cara.json").write_text(
        """
        {
          // Additional agent settings can be added alongside these defaults.
          agents: {
            defaults: {
              workspace: "~/cara-workspace",
              sandbox: {
                networkAccess: true,
                docker: {
                  binds: [
                    "~/Music:/music:ro",
                    "C:/projects:/projects:rw",
                  ],
                },
              },
            },
          },
        }
        """,
        encoding="utf-8",
    )

    configuration = load_cara_config(CaraPaths(state_root=state_root, _env_file=None))

    assert configuration.workspace_root == Path.home() / "cara-workspace"
    assert configuration.sandbox_network_access
    assert configuration.docker_binds == (
        DockerBind(source=Path.home() / "Music", target="/music"),
        DockerBind(source="C:/projects", target="/projects", writable=True),
    )


def test_environment_workspace_overrides_json5(
    monkeypatch,
    tmp_path: Path,
) -> None:
    state_root = tmp_path / "state"
    state_root.mkdir()
    (state_root / "cara.json").write_text(
        '{agents: {defaults: {workspace: "/from-file"}}}',
        encoding="utf-8",
    )
    monkeypatch.setenv("CARA_WORKSPACE_ROOT", str(tmp_path / "from-environment"))

    configuration = load_cara_config(CaraPaths(state_root=state_root, _env_file=None))

    assert configuration.workspace_root == tmp_path / "from-environment"


@pytest.mark.parametrize(
    "spec",
    [
        "/host:/container",
        "/host:relative:ro",
        "/host:/:ro",
        "/host:/container:invalid",
    ],
)
def test_rejects_invalid_docker_binds(spec: str) -> None:
    with pytest.raises(ValidationError):
        DockerBind.model_validate(spec)


def test_network_access_is_disabled_by_default(tmp_path: Path) -> None:
    configuration = load_cara_config(CaraPaths(state_root=tmp_path, _env_file=None))

    assert not configuration.sandbox_network_access
