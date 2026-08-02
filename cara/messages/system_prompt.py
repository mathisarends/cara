from pathlib import Path

from cara.markdown import render_tagged_section

_PROMPT_FILES = ("SOUL.md", "USER.md")


class SystemPrompt:
    """System prompt assembled from the markdown files next to this module."""

    def __init__(
        self,
        *,
        root: Path | None = None,
        override_system_prompt: str | None = None,
        extend_system_prompt: str | None = None,
    ) -> None:
        if override_system_prompt is not None and extend_system_prompt is not None:
            raise ValueError("Use either override_system_prompt or extend_system_prompt, not both.")
        self._root = root if root is not None else Path(__file__).parent
        self._override_system_prompt = override_system_prompt
        self._extend_system_prompt = extend_system_prompt

    def render(self) -> str:
        if self._override_system_prompt is not None:
            return self._override_system_prompt.strip()

        prompt = self._assemble()
        if self._extend_system_prompt is None:
            return prompt

        extension = self._extend_system_prompt.strip()
        if not extension:
            return prompt
        return f"{prompt}\n\n{extension}"

    def __str__(self) -> str:
        return self.render()

    def _assemble(self) -> str:
        sections = [
            section
            for file_name in _PROMPT_FILES
            if (section := render_tagged_section(self._root / file_name, tag=Path(file_name).stem.lower()))
        ]
        return "\n\n".join(sections)
