import asyncio
from pathlib import Path

from cara.file_system import Workspace
from cara.tools import Tools


def test_content_size_middleware_blocks_large_write(tmp_path: Path) -> None:
    tools = Tools(workspace=Workspace(tmp_path))

    result = asyncio.run(
        tools.execute(
            "write_file",
            {"path": "large.txt", "content": "x" * 1_000_001},
        )
    )

    assert not result.ok
    assert result.content is not None
    assert "exceeds the 1000000-byte write limit" in result.content
    assert not (tmp_path / "large.txt").exists()
