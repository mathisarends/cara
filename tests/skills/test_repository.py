from pathlib import Path

from cara.file_system import LocalFileSystem
from cara.skills import Skill, SkillRepository

_GREET = Skill(
    name="greet",
    description="Greet the user warmly.",
    instructions="Say hello in the user's language.",
)
_FAREWELL = Skill(
    name="farewell",
    description="Say goodbye.",
    instructions="Wish the user a good day.",
)


def test_holds_directly_provided_skills() -> None:
    repository = SkillRepository([_GREET, _FAREWELL])

    assert repository.get("greet") == _GREET
    assert repository.names() == ["farewell", "greet"]
    assert repository.get("unknown") is None


def test_render_catalog_lists_name_and_description() -> None:
    repository = SkillRepository([_GREET])

    assert repository.render_catalog() == "- greet: Greet the user warmly."


def _write_skill(root: Path, name: str, description: str, body: str) -> None:
    directory = root / "skills" / name
    directory.mkdir(parents=True)
    (directory / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {description}\n---\n\n{body}\n",
        encoding="utf-8",
    )


def test_discovers_skills_from_a_directory(tmp_path: Path) -> None:
    _write_skill(tmp_path, "pdf", "Read PDFs.", "Use the bundled parser.")
    (tmp_path / "skills" / "pdf" / "parser.py").write_text("# script", encoding="utf-8")
    _write_skill(tmp_path, "email", "Draft emails.", "Keep it concise.")

    repository = SkillRepository.from_directory(LocalFileSystem(tmp_path), "skills")

    assert repository.names() == ["email", "pdf"]
    pdf = repository.get("pdf")
    assert pdf is not None
    assert pdf.instructions == "Use the bundled parser."
    assert pdf.resources == ("parser.py",)


def test_directory_source_merges_with_direct_skills(tmp_path: Path) -> None:
    _write_skill(tmp_path, "pdf", "Read PDFs.", "Use the bundled parser.")

    repository = SkillRepository([_GREET])
    repository.load_directory(LocalFileSystem(tmp_path), "skills")

    assert repository.names() == ["greet", "pdf"]


def test_missing_directory_yields_no_skills(tmp_path: Path) -> None:
    repository = SkillRepository.from_directory(LocalFileSystem(tmp_path), "skills")

    assert repository.names() == []
