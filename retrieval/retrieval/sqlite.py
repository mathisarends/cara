import json
import sqlite3
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import TracebackType

import sqlite_vec

from retrieval import Document, Embedding, EmbeddingProvider, RetrievalResult, TextIndex


class SQLiteVectorIndex(TextIndex):
    """Persistent cosine-similarity index backed by SQLite and sqlite-vec."""

    def __init__(
        self,
        database: str | Path,
        embedding_provider: EmbeddingProvider,
        *,
        dimensions: int,
    ) -> None:
        if dimensions < 1:
            raise ValueError("dimensions must be at least 1")

        self._embedding_provider = embedding_provider
        self._dimensions = dimensions
        self._connection = sqlite3.connect(database)
        try:
            self._connection.row_factory = sqlite3.Row
            self._load_extension()
            self._create_schema()
        except BaseException:
            self._connection.close()
            raise

    async def index(self, documents: Sequence[Document]) -> None:
        items = list(documents)
        if not items:
            return

        indexed_at = datetime.now(UTC)
        rows = [
            (
                document.id,
                document.parent_id,
                document.text,
                _serialize_metadata(document.metadata),
                _serialize_datetime(document.created_at or indexed_at + timedelta(microseconds=position)),
            )
            for position, document in enumerate(items)
        ]

        embeddings = await self._embedding_provider.embed([document.text for document in items])
        if len(embeddings) != len(items):
            raise ValueError("Embedding provider returned an unexpected number of embeddings")
        self._validate_embeddings(embeddings)

        with self._connection:
            self._connection.executemany(
                """
                INSERT INTO documents (id, parent_id, text, metadata, created_at)
                VALUES (?, ?, ?, ?, COALESCE(?, CURRENT_TIMESTAMP))
                ON CONFLICT(id) DO UPDATE SET
                    parent_id = excluded.parent_id,
                    text = excluded.text,
                    metadata = excluded.metadata
                """,
                rows,
            )
            for document, embedding in zip(items, embeddings, strict=True):
                self._connection.execute(
                    "DELETE FROM document_embeddings WHERE document_id = ?",
                    (document.id,),
                )
                self._connection.execute(
                    """
                    INSERT INTO document_embeddings (document_id, embedding, parent_key)
                    VALUES (?, ?, ?)
                    """,
                    (
                        document.id,
                        sqlite_vec.serialize_float32(embedding),
                        _parent_key(document.parent_id),
                    ),
                )

    async def retrieve(self, query: str, *, limit: int = 5) -> list[RetrievalResult]:
        return await self.search(query, limit=limit)

    async def search(
        self,
        query: str,
        *,
        limit: int = 5,
        parent_id: str | None = None,
    ) -> list[RetrievalResult]:
        if limit < 1:
            raise ValueError("limit must be at least 1")

        existence_query = "SELECT EXISTS(SELECT 1 FROM document_embeddings"
        existence_parameters: tuple[object, ...] = ()
        if parent_id is not None:
            existence_query += " WHERE parent_key = ?"
            existence_parameters = (_parent_key(parent_id),)
        existence_query += ")"
        if not self._connection.execute(existence_query, existence_parameters).fetchone()[0]:
            return []

        embeddings = await self._embedding_provider.embed([query])
        if len(embeddings) != 1:
            raise ValueError("Embedding provider returned an unexpected number of embeddings")
        self._validate_embeddings(embeddings)

        parameters: list[object] = [sqlite_vec.serialize_float32(embeddings[0]), limit]
        parent_filter = ""
        if parent_id is not None:
            parent_filter = "AND parent_key = ?"
            parameters.append(_parent_key(parent_id))

        rows = self._connection.execute(
            f"""
            WITH matches AS (
                SELECT document_id, distance
                FROM document_embeddings
                WHERE embedding MATCH ?
                  AND k = ?
                  {parent_filter}
            )
            SELECT d.id, d.parent_id, d.text, d.metadata, d.created_at, matches.distance
            FROM matches
            JOIN documents AS d ON d.id = matches.document_id
            ORDER BY matches.distance
            """,
            parameters,
        ).fetchall()
        return [RetrievalResult(document=_document_from_row(row), score=1.0 - row["distance"]) for row in rows]

    async def get(self, document_id: str) -> Document | None:
        row = self._connection.execute(
            "SELECT id, parent_id, text, metadata, created_at FROM documents WHERE id = ?",
            (document_id,),
        ).fetchone()
        return None if row is None else _document_from_row(row)

    async def list_documents(
        self,
        *,
        parent_id: str | None = None,
        limit: int = 100,
    ) -> list[Document]:
        if limit < 1:
            raise ValueError("limit must be at least 1")

        if parent_id is None:
            rows = self._connection.execute(
                """
                SELECT id, parent_id, text, metadata, created_at
                FROM documents
                WHERE parent_id IS NULL
                ORDER BY created_at DESC, id
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        else:
            rows = self._connection.execute(
                """
                SELECT id, parent_id, text, metadata, created_at
                FROM documents
                WHERE parent_id = ?
                ORDER BY created_at, id
                LIMIT ?
                """,
                (parent_id, limit),
            ).fetchall()
        return [_document_from_row(row) for row in rows]

    async def delete(self, document_ids: Sequence[str]) -> None:
        ids = list(dict.fromkeys(document_ids))
        if not ids:
            return

        with self._connection:
            self._connection.executemany(
                "DELETE FROM document_embeddings WHERE document_id = ?",
                ((document_id,) for document_id in ids),
            )
            self._connection.executemany(
                "DELETE FROM documents WHERE id = ?",
                ((document_id,) for document_id in ids),
            )

    def close(self) -> None:
        self._connection.close()

    def __enter__(self) -> "SQLiteVectorIndex":
        return self

    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    def _load_extension(self) -> None:
        self._connection.enable_load_extension(True)
        try:
            sqlite_vec.load(self._connection)
        finally:
            self._connection.enable_load_extension(False)

    def _create_schema(self) -> None:
        with self._connection:
            self._connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS documents (
                    id TEXT PRIMARY KEY,
                    parent_id TEXT,
                    text TEXT NOT NULL,
                    metadata TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                CREATE INDEX IF NOT EXISTS documents_parent_id
                ON documents(parent_id);
                """
            )
            self._connection.execute(
                f"""
                CREATE VIRTUAL TABLE IF NOT EXISTS document_embeddings USING vec0(
                    document_id TEXT PRIMARY KEY,
                    embedding float[{self._dimensions}] distance_metric=cosine,
                    parent_key TEXT
                )
                """
            )
        self._validate_schema_dimensions()

    def _validate_schema_dimensions(self) -> None:
        row = self._connection.execute(
            "SELECT sql FROM sqlite_master WHERE name = 'document_embeddings'",
        ).fetchone()
        expected = f"float[{self._dimensions}]"
        if row is None or expected not in row["sql"].casefold():
            raise ValueError("The existing document_embeddings table uses different embedding dimensions")

    def _validate_embeddings(self, embeddings: Sequence[Embedding]) -> None:
        if any(len(embedding) != self._dimensions for embedding in embeddings):
            raise ValueError(f"Embedding vectors must have {self._dimensions} dimensions")


def _serialize_metadata(metadata: Mapping[str, object]) -> str:
    try:
        return json.dumps(dict(metadata), ensure_ascii=False, allow_nan=False, separators=(",", ":"))
    except (TypeError, ValueError) as error:
        raise ValueError("metadata must contain only JSON-serializable values") from error


def _deserialize_metadata(value: str | None) -> Mapping[str, object]:
    if value is None:
        return {}
    metadata = json.loads(value)
    if not isinstance(metadata, dict):
        raise ValueError("Stored document metadata must be a JSON object")
    return metadata


def _serialize_datetime(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        raise ValueError("created_at must include timezone information")
    return value.astimezone(UTC).strftime("%Y-%m-%d %H:%M:%S.%f")


def _deserialize_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value).replace(tzinfo=UTC)


def _document_from_row(row: sqlite3.Row) -> Document:
    return Document(
        id=row["id"],
        parent_id=row["parent_id"],
        text=row["text"],
        metadata=_deserialize_metadata(row["metadata"]),
        created_at=_deserialize_datetime(row["created_at"]),
    )


def _parent_key(parent_id: str | None) -> str:
    return "root" if parent_id is None else f"id:{parent_id}"
