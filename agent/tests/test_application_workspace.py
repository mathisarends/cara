import asyncio
from pathlib import PurePosixPath

import pytest
from agenttoolkit.builtins.fs import PathOutsideWorkspaceError
from main import _create_workspace, _editable_sandbox_mounts


def test_application_workspace_exposes_runtime_content_and_editable_code() -> None:
    workspace = _create_workspace()

    assert "Mathis" in asyncio.run(workspace.read_file("USER.md"))
    assert asyncio.run(workspace.read_file("/src/agent/agent.py")).startswith(
        "import json"
    )
    assert asyncio.run(
        workspace.read_file("/experiments/chat_in_terminal.py")
    ).startswith("import asyncio")
    assert asyncio.run(workspace.read_file("/skills/spogo-cli/SKILL.md")).startswith(
        "---"
    )


def test_application_workspace_does_not_expose_project_secrets() -> None:
    workspace = _create_workspace()

    with pytest.raises(PathOutsideWorkspaceError):
        asyncio.run(workspace.read_file("../.env"))


def test_application_sandbox_mounts_editable_code_only() -> None:
    mounts = _editable_sandbox_mounts()

    assert {mount.target for mount in mounts} == {
        PurePosixPath("/src/agent"),
        PurePosixPath("/experiments"),
        PurePosixPath("/skills"),
    }
    assert all(mount.writable for mount in mounts)
