from pathlib import Path

import pytest

from cara.file_system import FileSystem, LocalFileSystem, PathOutsideWorkspaceError, Workspace


def test_is_a_filesystem(tmp_path: Path) -> None:
    assert isinstance(LocalFileSystem(Workspace(tmp_path)), FileSystem)


def test_write_then_read_roundtrips(tmp_path: Path) -> None:
    fs = LocalFileSystem(Workspace(tmp_path))

    fs.write_text("notes/todo.md", "content")

    assert fs.read_text("notes/todo.md") == "content"
    assert (tmp_path / "notes" / "todo.md").read_text(encoding="utf-8") == "content"


def test_exists_and_is_dir(tmp_path: Path) -> None:
    fs = LocalFileSystem(Workspace(tmp_path))
    fs.write_text("skills/greet/SKILL.md", "hi")

    assert fs.exists("skills/greet/SKILL.md")
    assert fs.is_dir("skills/greet")
    assert not fs.is_dir("skills/greet/SKILL.md")
    assert not fs.exists("skills/missing")


def test_list_dir_is_sorted(tmp_path: Path) -> None:
    fs = LocalFileSystem(Workspace(tmp_path))
    fs.write_text("skills/greet/SKILL.md", "hi")
    fs.write_text("skills/farewell/SKILL.md", "bye")

    assert fs.list_dir("skills") == ["farewell", "greet"]


def test_read_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        LocalFileSystem(Workspace(tmp_path)).read_text("missing.md")


@pytest.mark.parametrize("path", ["../outside.txt", "../../outside.txt"])
def test_rejects_parent_traversal(tmp_path: Path, path: str) -> None:
    fs = LocalFileSystem(Workspace(tmp_path))

    with pytest.raises(PathOutsideWorkspaceError):
        fs.write_text(path, "content")


def test_rejects_absolute_paths(tmp_path: Path) -> None:
    fs = LocalFileSystem(Workspace(tmp_path))

    with pytest.raises(PathOutsideWorkspaceError):
        fs.read_text(str(tmp_path / "notes.md"))


def test_rejects_symlink_that_points_outside_workspace(tmp_path: Path) -> None:
    outside = tmp_path.parent / f"{tmp_path.name}-outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("secret", encoding="utf-8")
    link = tmp_path / "escape"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError as error:
        pytest.skip(f"Creating symlinks is not supported: {error}")

    fs = LocalFileSystem(Workspace(tmp_path))
    with pytest.raises(PathOutsideWorkspaceError):
        fs.read_text("escape/secret.txt")
