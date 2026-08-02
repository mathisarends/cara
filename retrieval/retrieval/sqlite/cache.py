import hashlib
from array import array
from collections.abc import Sequence
from pathlib import Path
from types import TracebackType

from retrieval import Embedding, EmbeddingProvider
from retrieval.sqlite._common import open_database

_CACHE = "embedding_cache"
_LOOKUP_BATCH = 500


class SQLiteEmbeddingCache(EmbeddingProvider):
    """Embedding provider that remembers what it has already embedded.

    Re-indexing a corpus normally re-embeds every unchanged chunk. Wrapping
    the real provider in this cache reduces that to the texts that actually
    changed, at the cost of one SQLite lookup per text.
    """

    def __init__(self, database: str | Path, embedding_provider: EmbeddingProvider, *, namespace: str) -> None:
        if not namespace:
            raise ValueError("namespace must not be empty")

        self._embedding_provider = embedding_provider
        self._namespace = namespace
        self._connection = open_database(database)

        try:
            self._create_schema()
        except BaseException:
            self._connection.close()
            raise

    async def embed(self, texts: Sequence[str]) -> list[Embedding]:
        requested = list(texts)
        if not requested:
            return []

        cached = self._load(set(requested))
        missing = [text for text in dict.fromkeys(requested) if text not in cached]
        if missing:
            embeddings = await self._embedding_provider.embed(missing)
            if len(embeddings) != len(missing):
                raise ValueError("Embedding provider returned an unexpected number of embeddings")

            fresh = dict(zip(missing, embeddings, strict=True))
            self._store(fresh)
            cached.update(fresh)

        return [cached[text] for text in requested]

    def close(self) -> None:
        self._connection.close()

    def __enter__(self) -> "SQLiteEmbeddingCache":
        return self

    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    def _create_schema(self) -> None:
        with self._connection:
            self._connection.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {_CACHE} (
                    namespace TEXT NOT NULL,
                    text_digest BLOB NOT NULL,
                    embedding BLOB NOT NULL,
                    PRIMARY KEY (namespace, text_digest)
                )
                """
            )

    def _load(self, texts: set[str]) -> dict[str, Embedding]:
        digests = {_digest(text): text for text in texts}
        keys = list(digests)
        cached: dict[str, Embedding] = {}

        for start in range(0, len(keys), _LOOKUP_BATCH):
            batch = keys[start : start + _LOOKUP_BATCH]
            placeholders = ", ".join("?" * len(batch))
            rows = self._connection.execute(
                f"SELECT text_digest, embedding FROM {_CACHE} WHERE namespace = ? AND text_digest IN ({placeholders})",
                [self._namespace, *batch],
            ).fetchall()
            cached.update({digests[row["text_digest"]]: _deserialize(row["embedding"]) for row in rows})

        return cached

    def _store(self, embeddings: dict[str, Embedding]) -> None:
        with self._connection:
            self._connection.executemany(
                f"""
                INSERT INTO {_CACHE} (namespace, text_digest, embedding)
                VALUES (?, ?, ?)
                ON CONFLICT(namespace, text_digest) DO UPDATE SET embedding = excluded.embedding
                """,
                [(self._namespace, _digest(text), _serialize(embedding)) for text, embedding in embeddings.items()],
            )


def _digest(text: str) -> bytes:
    return hashlib.sha256(text.encode("utf-8")).digest()


def _serialize(embedding: Embedding) -> bytes:
    return array("f", embedding).tobytes()


def _deserialize(value: bytes) -> Embedding:
    return array("f", value).tolist()
