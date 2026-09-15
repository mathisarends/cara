from sandbox_manager.features.files.application.errors import InvalidEditError
from sandbox_manager.features.files.application.models import FileEntry, FileMatch
from sandbox_manager.features.files.application.ports import WorkspaceFileSystem


class WorkspaceFileService:
    def __init__(self, file_system: WorkspaceFileSystem) -> None:
        self._file_system = file_system

    async def read(self, path: str) -> str:
        return await self._file_system.read(path)

    async def write(self, path: str, content: str) -> None:
        await self._file_system.write(path, content)

    async def edit(
        self,
        path: str,
        old: str,
        new: str,
        *,
        replace_all: bool,
    ) -> int:
        if not old:
            raise InvalidEditError("old text must not be empty")
        content = await self._file_system.read(path)
        occurrences = content.count(old)
        if occurrences == 0:
            raise InvalidEditError("old text was not found")
        if occurrences > 1 and not replace_all:
            raise InvalidEditError(f"old text occurs {occurrences} times")
        count = occurrences if replace_all else 1
        await self._file_system.write(path, content.replace(old, new, count))
        return count

    async def list_entries(self, path: str, *, recursive: bool) -> list[FileEntry]:
        return await self._file_system.list_entries(path, recursive=recursive)

    async def glob(self, pattern: str) -> list[FileEntry]:
        return await self._file_system.glob(pattern)

    async def grep(
        self,
        pattern: str,
        *,
        glob: str | None,
        case_sensitive: bool,
        context_lines: int,
        max_matches: int | None,
    ) -> list[FileMatch]:
        return await self._file_system.grep(
            pattern,
            glob=glob,
            case_sensitive=case_sensitive,
            context_lines=context_lines,
            max_matches=max_matches,
        )

    async def stat(self, path: str) -> FileEntry | None:
        return await self._file_system.stat(path)
