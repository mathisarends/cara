from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING

from obstore import sign_async

from gateway.platform.storage.object_storage import (
    ContentType,
    ObjectNotFoundError,
    ObjectStorage,
    StoredObject,
    _guess_content_type,
)

if TYPE_CHECKING:
    from obstore.store import ObjectStore

_LIST_CHUNK_SIZE = 1_000


class ObstoreObjectStorage(ObjectStorage):
    def __init__(
        self,
        store: ObjectStore,
        *,
        signing_store: ObjectStore | None = None,
    ) -> None:
        self._store = store
        self._signing_store = signing_store or store

    async def upload_bytes(
        self, path: str, data: bytes, content_type: ContentType | None = None
    ) -> str:
        await self._store.put_async(
            path,
            data,
            attributes={"Content-Type": str(content_type or ContentType.OCTET_STREAM)},
        )
        return path

    async def get_bytes(self, path: str) -> bytes:
        try:
            result = await self._store.get_async(path)
            return bytes(await result.bytes_async())
        except FileNotFoundError as error:
            raise ObjectNotFoundError(path) from error

    async def copy_file(self, source_path: str, destination_path: str) -> None:
        try:
            await self._store.copy_async(source_path, destination_path)
        except FileNotFoundError as error:
            raise ObjectNotFoundError(source_path) from error

    async def delete_file(self, path: str) -> None:
        try:
            await self._store.delete_async(path)
        except FileNotFoundError:
            return

    async def delete_folder(self, path: str) -> None:
        async for objects in self._store.list(path, chunk_size=_LIST_CHUNK_SIZE):
            paths = [obj["path"] for obj in objects if not obj["path"].endswith("/")]
            if paths:
                await self._store.delete_async(paths)

    async def list_files(self, path: str = "") -> list[StoredObject]:
        files: list[StoredObject] = []
        async for objects in self._store.list(
            path or None, chunk_size=_LIST_CHUNK_SIZE
        ):
            files.extend(
                StoredObject(
                    path=obj["path"],
                    name=obj["path"].rsplit("/", maxsplit=1)[-1],
                    size_bytes=obj["size"],
                    content_type=_guess_content_type(obj["path"]),
                    updated_at=obj["last_modified"],
                )
                for obj in objects
                if not obj["path"].endswith("/")
            )
        return files

    async def get_signed_url(self, path: str, ttl_seconds: int = 3600) -> str:
        try:
            await self._store.head_async(path)
        except FileNotFoundError as error:
            raise ObjectNotFoundError(path) from error

        return await sign_async(
            self._signing_store,
            "GET",
            path,
            expires_in=timedelta(seconds=ttl_seconds),
        )

    async def exists(self, path: str) -> bool:
        try:
            await self._store.head_async(path)
            return True
        except FileNotFoundError:
            return False
