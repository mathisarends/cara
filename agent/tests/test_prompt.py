from datetime import date
from pathlib import Path

import pytest
from agenttoolkit import Skills

from agent.prompt import SystemPrompt


def _composer(root: Path, **kwargs: object) -> SystemPrompt:
    return SystemPrompt(root=root, system_prompt="System", **kwargs)


def _skills(root: Path, name: str = "pdf", description: str = "Read PDFs.") -> Skills:
    directory = root / name
    directory.mkdir()
    (directory / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {description}\n---\nInstructions.\n",
        encoding="utf-8",
    )
    return Skills.from_dir(root)


def test_available_skills_are_appended_to_the_system_prompt(tmp_path: Path) -> None:
    rendered = _composer(tmp_path, skills=_skills(tmp_path)).render()

    assert rendered == (
        "System\n\n<available_skills>\n"
        "<skill>\n<name>pdf</name>\n<description>Read PDFs.</description>\n</skill>\n"
        "</available_skills>"
    )


def test_empty_skills_leaves_the_system_prompt_untouched(tmp_path: Path) -> None:
    composer = _composer(tmp_path, skills=Skills.from_dir(tmp_path))

    assert composer.render() == "System"


def test_system_prompt_is_assembled_from_the_context_markdown_files(
    tmp_path: Path,
) -> None:
    for name in ("AGENTS.md", "IDENTITY.md", "SOUL.md", "USER.md", "MEMORY.md"):
        (tmp_path / name).write_text(name, encoding="utf-8")

    prompt = SystemPrompt(root=tmp_path).render()

    assert (
        prompt.index("### AGENTS.md")
        < prompt.index("### SOUL.md")
        < prompt.index("### USER.md")
        < prompt.rindex("### MEMORY.md")
    )


def test_system_prompt_defaults_to_the_user_workspace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "AGENTS.md").write_text("Workspace rules.", encoding="utf-8")
    monkeypatch.setenv("CARA_WORKSPACE_ROOT", str(tmp_path))

    assert SystemPrompt().render() == "### AGENTS.md\n\nWorkspace rules."


def test_system_prompt_skips_files_that_are_missing(tmp_path: Path) -> None:
    (tmp_path / "USER.md").write_text("Mathis lebt in Berlin.", encoding="utf-8")

    assert (
        SystemPrompt(root=tmp_path).render() == "### USER.md\n\nMathis lebt in Berlin."
    )


def test_system_prompt_can_override_default_prompt_while_retaining_memory(
    tmp_path: Path,
) -> None:
    (tmp_path / "SOUL.md").write_text("Sei direkt.", encoding="utf-8")
    (tmp_path / "MEMORY.md").write_text("Halbmarathon im Oktober.", encoding="utf-8")

    prompt = SystemPrompt(root=tmp_path, system_prompt="Nur JSON.").render()

    assert prompt == "Nur JSON.\n\n### MEMORY.md\n\nHalbmarathon im Oktober."


def test_memory_renders_files_in_order(tmp_path: Path) -> None:
    (tmp_path / "MEMORY.md").write_text("Halbmarathon im Oktober.", encoding="utf-8")

    rendered = _composer(tmp_path).render()

    assert rendered == "System\n\n### MEMORY.md\n\nHalbmarathon im Oktober."


def test_dynamic_memory_follows_static_tools_and_skills(tmp_path: Path) -> None:
    (tmp_path / "TOOLS.md").write_text("Tool facts.", encoding="utf-8")
    (tmp_path / "MEMORY.md").write_text("Current memory.", encoding="utf-8")

    rendered = _composer(tmp_path, skills=_skills(tmp_path)).render()

    assert rendered.index("### TOOLS.md") < rendered.index("<available_skills>")
    assert rendered.index("<available_skills>") < rendered.index("### MEMORY.md")


def test_memory_includes_only_todays_daily_note(tmp_path: Path) -> None:
    memory = tmp_path / "memory"
    memory.mkdir()
    (memory / "2026-08-01.md").write_text("Gestern.", encoding="utf-8")
    (memory / "2026-08-02.md").write_text("Heute.", encoding="utf-8")

    rendered = _composer(tmp_path, today=lambda: date(2026, 8, 2)).render()

    assert rendered == "System\n\n### memory/2026-08-02.md\n\nHeute."


def test_memory_skips_missing_and_empty_files(tmp_path: Path) -> None:
    (tmp_path / "MEMORY.md").write_text("   \n", encoding="utf-8")

    assert _composer(tmp_path).render() == "System"


def test_workspace_memory_is_loaded(tmp_path: Path) -> None:
    (tmp_path / "MEMORY.md").write_text("Remember this.", encoding="utf-8")

    assert "### MEMORY.md" in SystemPrompt(root=tmp_path).render()
