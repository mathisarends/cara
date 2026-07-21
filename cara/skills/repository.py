from collections.abc import Iterable
from typing import Self

from cara.file_system import FileSystem
from cara.skills.models import Skill
from cara.skills.parser import parse_skill

_SKILL_MANIFEST = "SKILL.md"


class Skills:
    """A named collection of skills the ``load_skill`` action can draw from.

    Skills can be supplied directly as :class:`Skill` objects or discovered from
    a directory laid out as ``<root>/<skill>/SKILL.md`` on any :class:`FileSystem`.
    """

    def __init__(self, skills: Iterable[Skill] = ()) -> None:
        self._skills: dict[str, Skill] = {skill.name: skill for skill in skills}

    @classmethod
    def from_directory(cls, filesystem: FileSystem, root: str) -> Self:
        skills = cls()
        skills.load_directory(filesystem, root)
        return skills

    def add(self, skill: Skill) -> None:
        self._skills[skill.name] = skill

    def load_directory(self, filesystem: FileSystem, root: str) -> None:
        for skill in _discover(filesystem, root):
            self._skills[skill.name] = skill

    def all(self) -> list[Skill]:
        return list(self._skills.values())

    def get(self, name: str) -> Skill | None:
        return self._skills.get(name)

    def names(self) -> list[str]:
        return sorted(self._skills)

    def render_catalog(self) -> str:
        return "\n".join(skill.catalog_entry() for skill in self._skills.values())


def _discover(filesystem: FileSystem, root: str) -> list[Skill]:
    if not filesystem.is_dir(root):
        return []

    skills: list[Skill] = []
    for entry in filesystem.list_dir(root):
        directory = f"{root}/{entry}"
        manifest = f"{directory}/{_SKILL_MANIFEST}"
        if not filesystem.is_dir(directory) or not filesystem.exists(manifest):
            continue

        resources = tuple(name for name in filesystem.list_dir(directory) if name != _SKILL_MANIFEST)
        skills.append(parse_skill(filesystem.read_text(manifest), resources=resources))
    return skills
