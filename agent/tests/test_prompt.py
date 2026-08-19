from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from agenttoolkit import Skills

from agent.prompt import LocalTimePrompt, SystemPrompt

CONTEXT_ROOT = Path(__file__).parents[1] / "src" / "agent" / "prompt" / "context"


def _composer(root: Path, **kwargs: object) -> SystemPrompt:
    return SystemPrompt(root=root, system_prompt="System", **kwargs)


def _fixed_local_time() -> LocalTimePrompt:
    return LocalTimePrompt(
        timezone="Europe/Berlin",
        clock=lambda: datetime(2026, 7, 21, 14, 30, tzinfo=ZoneInfo("Europe/Berlin")),
    )


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


def test_local_time_prompt_renders_weekday_date_and_time() -> None:
    assert _fixed_local_time().render() == "Dienstag, 21. Juli 2026, 14:30 Uhr"


def test_local_time_is_rendered_as_its_own_section(tmp_path: Path) -> None:
    rendered = _composer(tmp_path, local_time=_fixed_local_time()).render()

    assert rendered == "System\n\n### Local Time\n\nDienstag, 21. Juli 2026, 14:30 Uhr"


def test_local_time_precedes_available_skills_in_the_system_prompt(
    tmp_path: Path,
) -> None:
    composer = _composer(
        tmp_path,
        skills=_skills(tmp_path, "weather", "Wetter ansagen."),
        local_time=_fixed_local_time(),
    )

    rendered = composer.render()

    assert rendered.index("### Local Time") < rendered.index("<available_skills>")


def test_system_prompt_is_assembled_from_the_context_markdown_files() -> None:
    prompt = SystemPrompt(root=CONTEXT_ROOT).render()

    assert (
        prompt.index("### AGENTS.md")
        < prompt.index("### SOUL.md")
        < prompt.index("### USER.md")
        < prompt.rindex("### MEMORY.md")
    )


def test_system_prompt_defaults_to_the_bundled_context_files() -> None:
    assert SystemPrompt().render() == SystemPrompt(root=CONTEXT_ROOT).render()


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


def test_memory_includes_only_todays_daily_note(tmp_path: Path) -> None:
    daily = tmp_path / "daily"
    daily.mkdir()
    (daily / "2026-08-01.md").write_text("Gestern.", encoding="utf-8")
    (daily / "2026-08-02.md").write_text("Heute.", encoding="utf-8")

    rendered = _composer(tmp_path, today=lambda: date(2026, 8, 2)).render()

    assert rendered == "System\n\n### daily/2026-08-02.md\n\nHeute."


def test_memory_skips_missing_and_empty_files(tmp_path: Path) -> None:
    (tmp_path / "MEMORY.md").write_text("   \n", encoding="utf-8")

    assert _composer(tmp_path).render() == "System"


def test_context_memory_is_loaded() -> None:
    assert "### MEMORY.md" in SystemPrompt(root=CONTEXT_ROOT).render()
