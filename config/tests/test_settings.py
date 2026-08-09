from pathlib import Path

from config import CaraPaths


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
