from abc import ABC, abstractmethod


class FileSystem(ABC):
    """Minimal read/write view over a tree of text files.

    Paths use ``/`` as the separator regardless of platform. Implementations
    back this with the local disk or an in-memory store so callers can be
    exercised without touching the real filesystem.
    """

    @abstractmethod
    def read_text(self, path: str) -> str: ...

    @abstractmethod
    def write_text(self, path: str, content: str) -> None: ...

    @abstractmethod
    def exists(self, path: str) -> bool: ...

    @abstractmethod
    def is_dir(self, path: str) -> bool: ...

    @abstractmethod
    def list_dir(self, path: str) -> list[str]: ...

    def tree(self, path: str) -> list[str]:
        """Recursively list entries under ``path``, relative to it.

        Directories are suffixed with ``/`` and precede their contents.
        """
        entries: list[str] = []
        for name in self.list_dir(path):
            child = f"{path}/{name}"
            if self.is_dir(child):
                entries.append(f"{name}/")
                entries.extend(f"{name}/{descendant}" for descendant in self.tree(child))
            else:
                entries.append(name)
        return entries
