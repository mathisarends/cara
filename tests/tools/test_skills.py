import asyncio

from cara.skills import Skill, SkillRepository
from cara.tools import Tools

_PDF = Skill(
    name="pdf",
    description="Read PDFs.",
    instructions="Use the bundled parser to extract text.",
)


def _tools_with_pdf() -> Tools:
    tools = Tools()
    tools.provide(SkillRepository([_PDF]))
    return tools


def _status() -> dict[str, str]:
    return {"status": "Einen Moment..."}


def test_skill_tools_are_always_registered() -> None:
    tools = Tools()

    assert tools.get("load_skill") is not None
    assert tools.get("remove_skill") is not None


def test_available_skills_are_listed_in_the_system_prompt_not_the_tool_description() -> None:
    tools = _tools_with_pdf()
    load_skill = tools.get("load_skill")

    assert load_skill is not None
    assert "pdf: Read PDFs." not in (load_skill.description or "")
    assert "# Available Skills\n\n- pdf: Read PDFs." in tools.render_skill_context()


def test_load_skill_brings_instructions_into_context() -> None:
    tools = _tools_with_pdf()

    result = asyncio.run(tools.execute("load_skill", {"name": "pdf", **_status()}))

    assert result.ok
    context = tools.render_skill_context()
    assert "# Active Skills\n\n## pdf\nUse the bundled parser to extract text." in context


def test_load_skill_without_a_provided_repository_fails() -> None:
    tools = Tools()

    result = asyncio.run(tools.execute("load_skill", {"name": "pdf", **_status()}))

    assert not result.ok


def test_loading_unknown_skill_fails() -> None:
    tools = _tools_with_pdf()

    result = asyncio.run(tools.execute("load_skill", {"name": "missing", **_status()}))

    assert not result.ok


def test_remove_skill_takes_it_back_out_of_context() -> None:
    tools = _tools_with_pdf()
    asyncio.run(tools.execute("load_skill", {"name": "pdf", **_status()}))

    result = asyncio.run(tools.execute("remove_skill", {"name": "pdf", **_status()}))

    assert result.ok
    assert "# Active Skills" not in tools.render_skill_context()


def test_removing_a_skill_that_is_not_loaded_fails() -> None:
    tools = _tools_with_pdf()

    result = asyncio.run(tools.execute("remove_skill", {"name": "pdf", **_status()}))

    assert not result.ok
