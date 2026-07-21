from collections.abc import Sequence

import yaml

from cara.skills.models import Skill

_FRONTMATTER_DELIMITER = "---"


class SkillParseError(ValueError):
    pass


def parse_skill(content: str, *, resources: Sequence[str] = ()) -> Skill:
    """Parse a ``SKILL.md`` document into a :class:`Skill`.

    The document follows the Agent Skills format: a YAML frontmatter block
    delimited by ``---`` lines carrying ``name`` and ``description``, followed
    by the Markdown instructions.
    """
    metadata, instructions = _split_frontmatter(content)

    name = metadata.get("name")
    description = metadata.get("description")
    if not isinstance(name, str) or not name.strip():
        raise SkillParseError("Skill frontmatter is missing a non-empty 'name'.")
    if not isinstance(description, str) or not description.strip():
        raise SkillParseError("Skill frontmatter is missing a non-empty 'description'.")

    return Skill(
        name=name.strip(),
        description=description.strip(),
        instructions=instructions.strip(),
        resources=tuple(resources),
    )


def _split_frontmatter(content: str) -> tuple[dict[str, object], str]:
    lines = content.splitlines()
    if not lines or lines[0].strip() != _FRONTMATTER_DELIMITER:
        raise SkillParseError("Skill document must start with a '---' frontmatter block.")

    for index in range(1, len(lines)):
        if lines[index].strip() != _FRONTMATTER_DELIMITER:
            continue
        block = "\n".join(lines[1:index])
        body = "\n".join(lines[index + 1 :])
        metadata = yaml.safe_load(block) or {}
        if not isinstance(metadata, dict):
            raise SkillParseError("Skill frontmatter must be a mapping of keys to values.")
        return metadata, body

    raise SkillParseError("Skill frontmatter block is not terminated by a closing '---'.")
