from pathlib import Path

from cli.onboarding import onboard


def test_onboard_creates_workspace(tmp_path: Path) -> None:
    root = tmp_path / ".cara" / "workspace"

    results = onboard(root)

    assert results == [
        (root / "AGENTS.md", True),
        (root / "IDENTITY.md", True),
        (root / "SOUL.md", True),
        (root / "USER.md", True),
        (root / "MEMORY.md", True),
        (root / "TOOLS.md", True),
        (root / "skills", True),
        (root / "skills" / "cli-skill-creator" / "SKILL.md", True),
        (
            root / "skills" / "cli-skill-creator" / "scripts" / "init_skill.py",
            True,
        ),
        (
            root / "skills" / "cli-skill-creator" / "scripts" / "quick_validate.py",
            True,
        ),
    ]
    for name in (
        "AGENTS.md",
        "IDENTITY.md",
        "SOUL.md",
        "USER.md",
        "MEMORY.md",
        "TOOLS.md",
    ):
        assert (root / name).read_text(encoding="utf-8")
    assert (root / "skills").is_dir()
    skill = root / "skills" / "cli-skill-creator"
    assert "Create a CLI Skill" in (skill / "SKILL.md").read_text(encoding="utf-8")
    assert (skill / "scripts" / "init_skill.py").is_file()
    assert (skill / "scripts" / "quick_validate.py").is_file()


def test_onboard_keeps_existing_files(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    root.mkdir()
    soul = root / "SOUL.md"
    soul.write_text("custom", encoding="utf-8")

    results = onboard(root)

    soul_result = next(result for result in results if result[0] == soul)
    assert soul_result == (soul, False)
    assert soul.read_text(encoding="utf-8") == "custom"
