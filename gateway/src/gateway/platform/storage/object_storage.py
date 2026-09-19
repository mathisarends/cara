import mimetypes
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class ObjectNotFoundError(Exception):
    def __init__(self, path: str) -> None:
        super().__init__(f"Storage object not found: {path}")
        self.path = path


@dataclass(frozen=True, slots=True)
class StoredObject:
    path: str
    name: str
    size_bytes: int
    content_type: str
    updated_at: datetime | None = None


class ContentType(StrEnum):
    OCTET_STREAM = "application/octet-stream"
    MPEG = "audio/mpeg"
    PDF = "application/pdf"
    GIF = "image/gif"
    ICO = "image/x-icon"
    JPEG = "image/jpeg"
    PNG = "image/png"
    MP4 = "video/mp4"
    SVG = "image/svg+xml"
    TEST_PLAIN = "text/plain"
    TEXT_PLAIN = "text/plain"
    MARKDOWN = "text/markdown"
    X_MARKDOWN = "text/x-markdown"
    WEBP = "image/webp"


class ObjectStorage(ABC):
    @abstractmethod
    async def upload_bytes(
        self, path: str, data: bytes, content_type: ContentType | None = None
    ) -> str: ...

    @abstractmethod
    async def get_bytes(self, path: str) -> bytes: ...

    @abstractmethod
    async def copy_file(self, source_path: str, destination_path: str) -> None: ...

    @abstractmethod
    async def delete_file(self, path: str) -> None: ...

    @abstractmethod
    async def delete_folder(self, path: str) -> None: ...

    @abstractmethod
    async def list_files(self, path: str = "") -> list[StoredObject]: ...

    @abstractmethod
    async def get_signed_url(self, path: str, ttl_seconds: int = 3600) -> str: ...

    @abstractmethod
    async def exists(self, path: str) -> bool: ...


def _guess_content_type(path: str) -> str:
    guessed, _ = mimetypes.guess_type(path)
    return guessed or str(ContentType.OCTET_STREAM)
