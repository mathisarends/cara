from collections.abc import Iterable

from sandbox_manager.features.files import application
from sandbox_manager.features.files.presentation.schemas import (
    FileEntry,
    FileMatch,
)


def to_file_entries(entries: Iterable[application.FileEntry]) -> list[FileEntry]:
    return [to_file_entry(entry) for entry in entries]


def to_file_entry(entry: application.FileEntry) -> FileEntry:
    return FileEntry(
        path=entry.path,
        is_dir=entry.is_dir,
        is_symlink=entry.is_symlink,
        size=entry.size,
        modified=entry.modified,
    )


def to_file_matches(matches: Iterable[application.FileMatch]) -> list[FileMatch]:
    return [
        FileMatch(
            path=match.path,
            line_number=match.line_number,
            line=match.line,
            context_before=match.context_before,
            context_after=match.context_after,
        )
        for match in matches
    ]
