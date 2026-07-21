import pytest

from cara.skills import Skill, SkillParseError, parse_skill

_DOCUMENT = """---
name: pdf-processing
description: Extract text and tables from PDF files.
---

# PDF Processing

Use the bundled script to pull structured data.
"""


def test_parses_metadata_and_instructions() -> None:
    skill = parse_skill(_DOCUMENT, resources=("extract.py",))

    assert skill == Skill(
        name="pdf-processing",
        description="Extract text and tables from PDF files.",
        instructions="# PDF Processing\n\nUse the bundled script to pull structured data.",
        resources=("extract.py",),
    )


def test_missing_frontmatter_raises() -> None:
    with pytest.raises(SkillParseError):
        parse_skill("# Just a heading\n")


def test_unterminated_frontmatter_raises() -> None:
    with pytest.raises(SkillParseError):
        parse_skill("---\nname: x\ndescription: y\n")


def test_missing_name_raises() -> None:
    with pytest.raises(SkillParseError):
        parse_skill("---\ndescription: only a description\n---\nbody")


def test_missing_description_raises() -> None:
    with pytest.raises(SkillParseError):
        parse_skill("---\nname: only-a-name\n---\nbody")
