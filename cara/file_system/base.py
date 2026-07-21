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
