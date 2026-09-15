from abc import ABC, abstractmethod

from sandbox_manager.features.files.application.models import FileEntry, FileMatch


class WorkspaceFileSystem(ABC):
    """Workspace-confined filesystem; paths are relative to the workspace root."""

    @abstractmethod
    async def read(self, path: str) -> str: ...

    @abstractmethod
    async def write(self, path: str, content: str) -> None: ...

    @abstractmethod
    async def list_entries(self, path: str, *, recursive: bool) -> list[FileEntry]: ...

    @abstractmethod
    async def glob(self, pattern: str) -> list[FileEntry]: ...

    @abstractmethod
    async def grep(
        self,
        pattern: str,
        *,
        glob: str | None,
        case_sensitive: bool,
        context_lines: int,
        max_matches: int | None,
    ) -> list[FileMatch]: ...

    @abstractmethod
    async def stat(self, path: str) -> FileEntry | None: ...
