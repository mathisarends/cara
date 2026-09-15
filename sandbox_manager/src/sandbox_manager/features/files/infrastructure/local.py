import asyncio
import re
from pathlib import Path

from sandbox_manager.features.files.application import (
    FileEntry,
    FileMatch,
    PathOutsideWorkspaceError,
    WorkspaceFileNotFoundError,
    WorkspaceFileSystem,
    WorkspaceNotADirectoryError,
)


class LocalWorkspaceFileSystem(WorkspaceFileSystem):
    def __init__(self, root: Path) -> None:
        self._root = root.resolve()

    async def read(self, path: str) -> str:
        return await asyncio.to_thread(self._resolve_file(path).read_text, "utf-8")

    async def write(self, path: str, content: str) -> None:
        target = self._resolve(path)
        await asyncio.to_thread(target.parent.mkdir, parents=True, exist_ok=True)
        await asyncio.to_thread(target.write_text, content, "utf-8")

    async def list_entries(self, path: str, *, recursive: bool) -> list[FileEntry]:
        return await asyncio.to_thread(self._list, path, recursive)

    async def glob(self, pattern: str) -> list[FileEntry]:
        if Path(pattern).is_absolute() or ".." in Path(pattern).parts:
            raise PathOutsideWorkspaceError(pattern)
        return await asyncio.to_thread(
            lambda: sorted(
                (self._entry(path) for path in self._root.glob(pattern)),
                key=lambda entry: entry.path,
            )
        )

    async def grep(
        self,
        pattern: str,
        *,
        glob: str | None,
        case_sensitive: bool,
        context_lines: int,
        max_matches: int | None,
    ) -> list[FileMatch]:
        return await asyncio.to_thread(
            self._grep,
            pattern,
            glob,
            case_sensitive,
            context_lines,
            max_matches,
        )

    async def stat(self, path: str) -> FileEntry | None:
        target = self._resolve(path)
        return await asyncio.to_thread(self._entry, target) if target.exists() else None

    def _resolve_file(self, path: str) -> Path:
        target = self._resolve(path)
        if not target.is_file():
            raise WorkspaceFileNotFoundError(path)
        return target

    def _resolve(self, path: str) -> Path:
        target = (self._root / path).resolve()
        if not target.is_relative_to(self._root):
            raise PathOutsideWorkspaceError(path)
        return target

    def _list(self, path: str, recursive: bool) -> list[FileEntry]:
        directory = self._resolve(path)
        if not directory.is_dir():
            raise WorkspaceNotADirectoryError(path)
        paths = directory.rglob("*") if recursive else directory.iterdir()
        return sorted((self._entry(item) for item in paths), key=lambda item: item.path)

    def _entry(self, path: Path) -> FileEntry:
        metadata = path.lstat()
        return FileEntry(
            path=path.relative_to(self._root).as_posix(),
            is_dir=path.is_dir(),
            is_symlink=path.is_symlink(),
            size=None if path.is_dir() else metadata.st_size,
            modified=metadata.st_mtime,
        )

    def _grep(
        self,
        pattern: str,
        glob: str | None,
        case_sensitive: bool,
        context_lines: int,
        max_matches: int | None,
    ) -> list[FileMatch]:
        regex = re.compile(pattern, 0 if case_sensitive else re.IGNORECASE)
        candidates = self._root.glob(glob or "**/*")
        matches: list[FileMatch] = []
        for candidate in candidates:
            if not candidate.is_file():
                continue
            try:
                lines = candidate.read_text(encoding="utf-8").splitlines()
            except (OSError, UnicodeDecodeError):
                continue
            for index, line in enumerate(lines):
                if regex.search(line):
                    matches.append(
                        FileMatch(
                            path=candidate.relative_to(self._root).as_posix(),
                            line_number=index + 1,
                            line=line,
                            context_before=tuple(
                                lines[max(0, index - context_lines) : index]
                            ),
                            context_after=tuple(
                                lines[index + 1 : index + 1 + context_lines]
                            ),
                        )
                    )
                    if max_matches is not None and len(matches) >= max_matches:
                        return matches
        return matches
