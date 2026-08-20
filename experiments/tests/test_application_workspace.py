import asyncio
from pathlib import Path, PurePosixPath

import pytest
from agenttoolkit.builtins.fs import PathOutsideWorkspaceError

from agent.sandbox import SandboxDefinition
from experiments.chat_in_terminal import _create_workspace

_PROJECT_CONFIG = Path(__file__).resolve().parents[2] / "sandbox.yml"


def test_application_workspace_exposes_runtime_content_and_editable_code(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CARA_WORKSPACE_ROOT", str(tmp_path))
    (tmp_path / "USER.md").write_text("Mathis", encoding="utf-8")
    workspace = _create_workspace()

    assert "Mathis" in asyncio.run(workspace.read_file("USER.md"))
    agent_source = asyncio.run(workspace.read_file("/src/agent/agent.py"))
    assert "class Agent:" in agent_source
    assert asyncio.run(
        workspace.read_file("/experiments/chat_in_terminal.py")
    ).startswith("import asyncio")
    assert asyncio.run(
        workspace.read_file("/skills/cli-skill-creator/SKILL.md")
    ).startswith("---")


def test_application_workspace_does_not_expose_project_secrets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CARA_WORKSPACE_ROOT", str(tmp_path))
    workspace = _create_workspace()

    with pytest.raises(PathOutsideWorkspaceError):
        asyncio.run(workspace.read_file("../.env"))


def test_application_sandbox_mounts_editable_code_only() -> None:
    mounts = SandboxDefinition.from_yaml(_PROJECT_CONFIG).mounts.paths

    assert {mount.target for mount in mounts} == {
        PurePosixPath("/src/agent"),
        PurePosixPath("/experiments"),
        PurePosixPath("/skills"),
    }
    assert all(mount.writable for mount in mounts)
