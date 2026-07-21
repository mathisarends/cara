import asyncio
from pathlib import Path

from cara.file_system import Workspace
from cara.tools import Tools


def test_path_policy_blocks_escape_before_file_tool_runs(tmp_path: Path) -> None:
    tools = Tools(workspace=Workspace(tmp_path))
    outside_name = f"{tmp_path.name}-outside.txt"

    result = asyncio.run(
        tools.execute(
            "write_file",
            {"path": f"../{outside_name}", "content": "unsafe", "status": "Writing..."},
        )
    )

    assert not result.ok
    assert result.content is not None
    assert "outside the workspace" in result.content
    assert not (tmp_path.parent / outside_name).exists()


def test_path_policy_blocks_sensitive_file(tmp_path: Path) -> None:
    tools = Tools(workspace=Workspace(tmp_path))

    result = asyncio.run(
        tools.execute(
            "write_file",
            {"path": ".env", "content": "SECRET=value", "status": "Writing..."},
        )
    )

    assert not result.ok
    assert result.content is not None
    assert "blocked by the workspace path policy" in result.content
    assert not (tmp_path / ".env").exists()


def test_path_policy_matches_sensitive_paths_case_insensitively(tmp_path: Path) -> None:
    tools = Tools(workspace=Workspace(tmp_path))

    result = asyncio.run(
        tools.execute(
            "write_file",
            {"path": ".ENV", "content": "SECRET=value", "status": "Writing..."},
        )
    )

    assert not result.ok
    assert not (tmp_path / ".ENV").exists()
