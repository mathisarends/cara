from pathlib import Path


def render_tagged_section(path: Path, *, tag: str) -> str:
    """Wrap a markdown file in a tag, or return an empty string when it is missing or blank."""
    if not path.is_file():
        return ""
    content = path.read_text(encoding="utf-8").strip()
    if not content:
        return ""
    return f"<{tag}>\n{content}\n</{tag}>"
