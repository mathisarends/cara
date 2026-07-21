from pathlib import Path


class PathOutsideWorkspaceError(ValueError):
    def __init__(self, path: str) -> None:
        super().__init__(f"Path {path!r} is outside the workspace.")
        self.path = path


class Workspace:
    """Resolve untrusted relative paths below one fixed filesystem root."""

    def __init__(self, root: str | Path) -> None:
        self._root = Path(root).resolve(strict=True)
        if not self._root.is_dir():
            raise NotADirectoryError(self._root)

    @property
    def root(self) -> Path:
        return self._root

    def resolve(self, candidate: str) -> Path:
        raw = Path(candidate)
        if raw.is_absolute():
            raise PathOutsideWorkspaceError(candidate)

        resolved = (self._root / raw).resolve(strict=False)
        if not resolved.is_relative_to(self._root):
            raise PathOutsideWorkspaceError(candidate)
        return resolved
