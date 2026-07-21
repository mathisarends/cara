from pathlib import Path

import pytest

from cara.file_system import FileSystem, LocalFileSystem


def test_is_a_filesystem() -> None:
    assert isinstance(LocalFileSystem(), FileSystem)


def test_write_then_read_roundtrips(tmp_path: Path) -> None:
    fs = LocalFileSystem(tmp_path)

    fs.write_text("notes/todo.md", "content")

    assert fs.read_text("notes/todo.md") == "content"
    assert (tmp_path / "notes" / "todo.md").read_text(encoding="utf-8") == "content"


def test_exists_and_is_dir(tmp_path: Path) -> None:
    fs = LocalFileSystem(tmp_path)
    fs.write_text("skills/greet/SKILL.md", "hi")

    assert fs.exists("skills/greet/SKILL.md")
    assert fs.is_dir("skills/greet")
    assert not fs.is_dir("skills/greet/SKILL.md")
    assert not fs.exists("skills/missing")


def test_list_dir_is_sorted(tmp_path: Path) -> None:
    fs = LocalFileSystem(tmp_path)
    fs.write_text("skills/greet/SKILL.md", "hi")
    fs.write_text("skills/farewell/SKILL.md", "bye")

    assert fs.list_dir("skills") == ["farewell", "greet"]


def test_read_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        LocalFileSystem(tmp_path).read_text("missing.md")
