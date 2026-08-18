from collections.abc import Callable
from datetime import date
from pathlib import Path

from agenttoolkit import Skills

from agent.prompt.local_time import LocalTimePrompt

_CONTEXT_ROOT = Path(__file__).parent / "context"
_BASE_FILES = ("AGENTS.md", "IDENTITY.md", "SOUL.md", "USER.md")
_TOOLS_FILES = ("TOOLS.md",)
_MEMORY_FILES = ("MEMORY.md",)
_DAILY_DIR = "daily"


class SystemPrompt:
    """Compose the agent's system prompt from all static and runtime context sources."""

    def __init__(
        self,
        *,
        root: Path | None = None,
        system_prompt: str | None = None,
        skills: Skills | None = None,
        local_time: LocalTimePrompt | None = None,
        today: Callable[[], date] | None = None,
    ) -> None:
        self._root = root or _CONTEXT_ROOT
        self._system_prompt = system_prompt
        self._skills = skills
        self._local_time = local_time
        self._today = today or date.today

    def render(self) -> str:
        sections = [self._render_base_prompt()]
        if self._local_time is not None:
            sections.append(f"<local_time>\n{self._local_time.render()}\n</local_time>")
        if memory := self._render_memory():
            sections.append(memory)
        if tools := _render_files(self._root, _TOOLS_FILES):
            sections.append(tools)
        if self._skills is not None and (catalog := self._skills.render_prompt()):
            sections.append(catalog)
        return "\n\n".join(section for section in sections if section)

    def __str__(self) -> str:
        return self.render()

    def _render_base_prompt(self) -> str:
        if self._system_prompt is not None:
            return self._system_prompt.strip()
        return _render_files(self._root, _BASE_FILES)

    def _render_memory(self) -> str:
        sections = [_render_files(self._root, _MEMORY_FILES)]
        daily_path = self._root / _DAILY_DIR / f"{self._today():%Y-%m-%d}.md"
        if daily := _render_tagged_section(daily_path, tag=_DAILY_DIR):
            sections.append(daily)
        return "\n\n".join(section for section in sections if section)


def _render_files(root: Path, file_names: tuple[str, ...]) -> str:
    sections = [
        section
        for file_name in file_names
        if (
            section := _render_tagged_section(
                root / file_name, tag=Path(file_name).stem.lower()
            )
        )
    ]
    return "\n\n".join(sections)


def _render_tagged_section(path: Path, *, tag: str) -> str:
    """Wrap a markdown file in a tag, or return an empty string when it is
    missing or blank."""
    if not path.is_file():
        return ""
    content = path.read_text(encoding="utf-8").strip()
    if not content:
        return ""
    return f"<{tag}>\n{content}\n</{tag}>"
