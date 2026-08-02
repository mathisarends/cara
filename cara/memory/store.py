from collections.abc import Callable
from datetime import date
from pathlib import Path

from cara.markdown import render_tagged_section

_MEMORY_FILES = ("MEMORY.md", "DREAMS.md")
_DAILY_DIR = "daily"


class MemoryStore:
    """Markdown memory files, rendered fresh on every turn so edits take effect immediately."""

    def __init__(self, *, root: Path | None = None, today: Callable[[], date] | None = None) -> None:
        self._root = root if root is not None else Path(__file__).parent
        self._today = today or date.today

    def render(self) -> str:
        sections = [
            section
            for file_name in _MEMORY_FILES
            if (section := render_tagged_section(self._root / file_name, tag=Path(file_name).stem.lower()))
        ]
        daily_path = self._root / _DAILY_DIR / f"{self._today():%Y-%m-%d}.md"
        if daily := render_tagged_section(daily_path, tag=_DAILY_DIR):
            sections.append(daily)
        return "\n\n".join(sections)
