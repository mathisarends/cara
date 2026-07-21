from pathlib import Path

from cara.file_system.base import FileSystem
from cara.file_system.workspace import Workspace


class LocalFileSystem(FileSystem):
    def __init__(self, workspace: Workspace) -> None:
        self._workspace = workspace

    def read_text(self, path: str) -> str:
        return self._resolve(path).read_text(encoding="utf-8")

    def write_text(self, path: str, content: str) -> None:
        target = self._resolve(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")

    def exists(self, path: str) -> bool:
        return self._resolve(path).exists()

    def is_dir(self, path: str) -> bool:
        return self._resolve(path).is_dir()

    def list_dir(self, path: str) -> list[str]:
        return sorted(entry.name for entry in self._resolve(path).iterdir())

    def _resolve(self, path: str) -> Path:
        return self._workspace.resolve(path)
