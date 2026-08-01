import asyncio
from pathlib import Path

from agenttoolkit import Skills

from cara.tools import Tools


def _skills(tmp_path: Path) -> Skills:
    directory = tmp_path / "pdf"
    directory.mkdir()
    (directory / "SKILL.md").write_text(
        "---\nname: pdf\ndescription: Read PDFs.\n---\nUse the bundled parser to extract text.\n",
        encoding="utf-8",
    )
    return Skills.from_local_dir(tmp_path)


def test_load_skill_tool_is_unavailable_without_skills() -> None:
    tools = Tools()

    assert tools.get("load_skill") is not None
    assert all(schema["function"]["name"] != "load_skill" for schema in tools.get_schema("openai"))


def test_load_skill_tool_is_available_with_skills(tmp_path: Path) -> None:
    tools = Tools()
    tools.provide(_skills(tmp_path))

    assert tools.get("load_skill") in tools.get_available()


def test_load_skill_returns_full_instructions(tmp_path: Path) -> None:
    tools = Tools()
    tools.provide(_skills(tmp_path))

    result = asyncio.run(tools.execute("load_skill", {"name": "pdf"}))

    assert result.result == "Use the bundled parser to extract text."


def test_loading_unknown_skill_fails(tmp_path: Path) -> None:
    tools = Tools()
    tools.provide(_skills(tmp_path))

    result = asyncio.run(tools.execute("load_skill", {"name": "missing"}))

    assert not result.ok
    assert result.error is not None
    assert "not found" in result.error
