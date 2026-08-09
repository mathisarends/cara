from importlib.resources import files
from pathlib import Path

_TEMPLATE_NAMES = (
    "AGENTS.md",
    "IDENTITY.md",
    "SOUL.md",
    "USER.md",
    "MEMORY.md",
    "TOOLS.md",
)
_INITIAL_SKILL_FILES = (
    Path("SKILL.md"),
    Path("scripts/init_skill.py"),
    Path("scripts/quick_validate.py"),
)


def workspace_root() -> Path:
    return Path.home() / ".cara" / "workspace"


def initial_skill_root() -> Path:
    return Path(__file__).resolve().parents[3] / "skills" / "cli-skill-creator"


def onboard(root: Path | None = None) -> list[tuple[Path, bool]]:
    selected_root = root or workspace_root()
    skill_root = initial_skill_root()
    missing_skill_files = [
        str(path) for path in _INITIAL_SKILL_FILES if not (skill_root / path).is_file()
    ]
    if missing_skill_files:
        raise RuntimeError(
            "Initial cli-skill-creator files are missing: "
            + ", ".join(missing_skill_files)
        )
    results: list[tuple[Path, bool]] = []
    selected_root.mkdir(parents=True, exist_ok=True)

    templates = files("cli.templates")
    for name in _TEMPLATE_NAMES:
        destination = selected_root / name
        created = not destination.exists()
        if created:
            destination.write_text(
                templates.joinpath(name).read_text(encoding="utf-8"),
                encoding="utf-8",
            )
        results.append((destination, created))

    skills = selected_root / "skills"
    created = not skills.exists()
    skills.mkdir(exist_ok=True)
    results.append((skills, created))

    target_skill = skills / "cli-skill-creator"
    for relative_path in _INITIAL_SKILL_FILES:
        destination = target_skill / relative_path
        created = not destination.exists()
        if created:
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(
                (skill_root / relative_path).read_text(encoding="utf-8"),
                encoding="utf-8",
            )
        results.append((destination, created))
    return results
