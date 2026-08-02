from collections.abc import Callable
from datetime import date
from pathlib import Path

from agenttoolkit import Skills

from cara.markdown import render_tagged_section
from cara.prompt.context import RuntimeContext

_IDENTITY_FILES = ("SOUL.md", "USER.md")
_MEMORY_FILES = ("MEMORY.md", "DREAMS.md")
_DAILY_DIR = "daily"


class SystemPromptComposer:
    """Compose the agent's system prompt from all static and runtime context sources."""

    def __init__(
        self,
        *,
        root: Path | None = None,
        system_prompt: str | None = None,
        override_system_prompt: str | None = None,
        extend_system_prompt: str | None = None,
        skills: Skills | None = None,
        context: RuntimeContext | None = None,
        today: Callable[[], date] | None = None,
    ) -> None:
        if system_prompt is not None and (override_system_prompt is not None or extend_system_prompt is not None):
            raise ValueError("Use system_prompt or override_system_prompt/extend_system_prompt, not both.")
        if override_system_prompt is not None and extend_system_prompt is not None:
            raise ValueError("Use either override_system_prompt or extend_system_prompt, not both.")
        self._root = root if root is not None else Path(__file__).parent
        self._system_prompt = system_prompt
        self._override_system_prompt = override_system_prompt
        self._extend_system_prompt = extend_system_prompt
        self._skills = skills
        self._context = context
        self._today = today or date.today

    def render(self) -> str:
        sections = [self._render_base_prompt()]
        if self._context is not None and (context := self._context.render()):
            sections.append(f"<context>\n{context}\n</context>")
        if memory := self._render_memory():
            sections.append(f"<memory>\n{memory}\n</memory>")
        if self._skills is not None and (catalog := self._skills.render_prompt()):
            sections.append(catalog)
        return "\n\n".join(section for section in sections if section)

    def __str__(self) -> str:
        return self.render()

    def _render_base_prompt(self) -> str:
        if self._system_prompt is not None:
            return self._system_prompt.strip()
        if self._override_system_prompt is not None:
            return self._override_system_prompt.strip()

        prompt = _render_files(self._root, _IDENTITY_FILES)
        if self._extend_system_prompt is None:
            return prompt

        extension = self._extend_system_prompt.strip()
        if not extension:
            return prompt
        return "\n\n".join(section for section in (prompt, extension) if section)

    def _render_memory(self) -> str:
        sections = [_render_files(self._root, _MEMORY_FILES)]
        daily_path = self._root / _DAILY_DIR / f"{self._today():%Y-%m-%d}.md"
        if daily := render_tagged_section(daily_path, tag=_DAILY_DIR):
            sections.append(daily)
        return "\n\n".join(section for section in sections if section)


def _render_files(root: Path, file_names: tuple[str, ...]) -> str:
    sections = [
        section
        for file_name in file_names
        if (section := render_tagged_section(root / file_name, tag=Path(file_name).stem.lower()))
    ]
    return "\n\n".join(sections)
