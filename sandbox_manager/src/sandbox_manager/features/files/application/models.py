from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class FileEntry:
    path: str
    is_dir: bool
    is_symlink: bool
    size: int | None
    modified: float


@dataclass(frozen=True, slots=True)
class FileMatch:
    path: str
    line_number: int
    line: str
    context_before: tuple[str, ...]
    context_after: tuple[str, ...]
