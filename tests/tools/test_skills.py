import asyncio

from cara.skills import Skill, Skills
from cara.tools import Tools

_PDF = Skill(
    name="pdf",
    description="Read PDFs.",
    instructions="Use the bundled parser to extract text.",
)


def _tools_with_pdf() -> Tools:
    tools = Tools()
    tools.provide(Skills([_PDF]))
    return tools


def test_load_skill_tool_is_always_registered() -> None:
    assert Tools().get("load_skill") is not None


def test_remove_skill_tool_no_longer_exists() -> None:
    assert Tools().get("remove_skill") is None


def test_available_skills_are_not_duplicated_in_the_tool_description() -> None:
    load_skill = _tools_with_pdf().get("load_skill")

    assert load_skill is not None
    assert "pdf: Read PDFs." not in (load_skill.description or "")


def test_load_skill_returns_the_full_instructions_as_its_result() -> None:
    tools = _tools_with_pdf()

    result = asyncio.run(tools.execute("load_skill", {"name": "pdf"}))

    assert result.ok
    assert result.content == "Use the bundled parser to extract text."


def test_load_skill_without_provided_skills_fails() -> None:
    result = asyncio.run(Tools().execute("load_skill", {"name": "pdf"}))

    assert not result.ok


def test_loading_unknown_skill_fails() -> None:
    tools = _tools_with_pdf()

    result = asyncio.run(tools.execute("load_skill", {"name": "missing"}))

    assert not result.ok
