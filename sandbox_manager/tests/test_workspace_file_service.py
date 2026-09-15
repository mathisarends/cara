from pathlib import Path

import pytest

from sandbox_manager.features.files.application import (
    InvalidEditError,
    PathOutsideWorkspaceError,
    WorkspaceFileService,
)
from sandbox_manager.features.files.infrastructure import LocalWorkspaceFileSystem


@pytest.fixture
def files(tmp_path: Path) -> WorkspaceFileService:
    return WorkspaceFileService(LocalWorkspaceFileSystem(tmp_path))


async def test_edit_replaces_a_unique_occurrence(files: WorkspaceFileService) -> None:
    await files.write("notes.txt", "alpha beta")

    count = await files.edit("notes.txt", "beta", "gamma", replace_all=False)

    assert count == 1
    assert await files.read("notes.txt") == "alpha gamma"


async def test_edit_rejects_ambiguous_text(files: WorkspaceFileService) -> None:
    await files.write("notes.txt", "x x")

    with pytest.raises(InvalidEditError, match="occurs 2 times"):
        await files.edit("notes.txt", "x", "y", replace_all=False)


async def test_paths_cannot_escape_the_workspace(
    files: WorkspaceFileService,
) -> None:
    with pytest.raises(PathOutsideWorkspaceError):
        await files.read("../outside.txt")
