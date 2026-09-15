import asyncio
from pathlib import Path

from agenttoolkit import Skills

from gateway.agent_runtime.tools import build_tools


def _skills(tmp_path: Path) -> Skills:
    directory = tmp_path / "pdf"
    directory.mkdir()
    (directory / "SKILL.md").write_text(
        "---\nname: pdf\ndescription: Read PDFs.\n---\n"
        "Use the bundled parser to extract text.\n",
        encoding="utf-8",
    )
    return Skills.from_dir(tmp_path)


def test_load_skill_tool_is_unavailable_without_skills(make_tool_context) -> None:
    tools = build_tools(context=make_tool_context())

    assert tools.get("load_skill") is not None
    assert all(
        schema["function"]["name"] != "load_skill"
        for schema in tools.get_schema("openai")
    )


def test_load_skill_tool_is_available_with_skills(
    tmp_path: Path, make_tool_context
) -> None:
    tools = build_tools(context=make_tool_context(_skills(tmp_path)))

    assert "load_skill" in {schema.name for schema in tools.get_schema()}


def test_load_skill_returns_full_instructions(
    tmp_path: Path, make_tool_context
) -> None:
    tools = build_tools(context=make_tool_context(_skills(tmp_path)))

    result = asyncio.run(tools.execute("load_skill", {"name": "pdf"}))

    assert result == "Use the bundled parser to extract text."


def test_loading_unknown_skill_fails(tmp_path: Path, make_tool_context) -> None:
    tools = build_tools(context=make_tool_context(_skills(tmp_path)))

    result = asyncio.run(tools.execute("load_skill", {"name": "missing"}))

    assert result.startswith("Tool failed:")
