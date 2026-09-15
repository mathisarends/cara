from collections.abc import Callable
from datetime import date
from pathlib import Path

from agenttoolkit import Skills

_BASE_FILES = ("AGENTS.md", "IDENTITY.md", "SOUL.md", "USER.md")
_TOOLS_FILES = ("TOOLS.md",)
_MEMORY_FILES = ("MEMORY.md",)
_MEMORY_DIR = "memory"


class SystemPrompt:
    """Compose the agent's system prompt from all static and runtime context sources."""

    def __init__(
        self,
        *,
        root: Path,
        system_prompt: str | None = None,
        skills: Skills | None = None,
        today: Callable[[], date] | None = None,
    ) -> None:
        self._root = root
        self._system_prompt = system_prompt
        self._skills = skills
        self._today = today or date.today

    def render(self) -> str:
        sections = [self._render_base_prompt()]
        if tools := _render_files(self._root, _TOOLS_FILES):
            sections.append(tools)
        if self._skills is not None and (catalog := self._skills.render_prompt()):
            sections.append(catalog)
        if memory := self._render_memory():
            sections.append(memory)
        return "\n\n".join(section for section in sections if section)

    def __str__(self) -> str:
        return self.render()

    def _render_base_prompt(self) -> str:
        if self._system_prompt is not None:
            return self._system_prompt.strip()
        return _render_files(self._root, _BASE_FILES)

    def _render_memory(self) -> str:
        daily_name = f"{self._today():%Y-%m-%d}.md"
        sections = [
            _render_files(self._root, _MEMORY_FILES),
            _render_section(
                self._root / _MEMORY_DIR / daily_name,
                heading=f"{_MEMORY_DIR}/{daily_name}",
            ),
        ]
        return "\n\n".join(section for section in sections if section)


def _render_files(root: Path, file_names: tuple[str, ...]) -> str:
    sections = [
        section
        for file_name in file_names
        if (section := _render_section(root / file_name, heading=file_name))
    ]
    return "\n\n".join(sections)


def _render_section(path: Path, *, heading: str) -> str:
    """Render a markdown file under a heading naming it, or return an empty
    string when it is missing or blank."""
    if not path.is_file():
        return ""
    content = path.read_text(encoding="utf-8").strip()
    if not content:
        return ""
    return f"### {heading}\n\n{content}"
