from collections.abc import Callable
from datetime import date
from pathlib import Path

_CORE_FILES = ("SOUL.md", "USER.md", "MEMORY.md", "DREAMS.md")
_DAILY_DIR = "daily"


class MemoryStore:
    """Markdown memory files, rendered fresh on every turn so edits take effect immediately."""

    def __init__(self, *, root: Path | None = None, today: Callable[[], date] | None = None) -> None:
        self._root = root if root is not None else Path(__file__).parent
        self._today = today or date.today

    def render(self) -> str:
        sections = [
            section
            for file_name in _CORE_FILES
            if (section := _render_file(self._root / file_name, tag=Path(file_name).stem.lower()))
        ]
        daily_path = self._root / _DAILY_DIR / f"{self._today():%Y-%m-%d}.md"
        if daily := _render_file(daily_path, tag=_DAILY_DIR):
            sections.append(daily)
        return "\n\n".join(sections)


def _render_file(path: Path, *, tag: str) -> str:
    if not path.is_file():
        return ""
    content = path.read_text(encoding="utf-8").strip()
    if not content:
        return ""
    return f"<{tag}>\n{content}\n</{tag}>"
