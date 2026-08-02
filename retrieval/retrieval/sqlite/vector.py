from collections.abc import Sequence
from pathlib import Path
from types import TracebackType

import sqlite_vec

from retrieval import Document, Embedding, EmbeddingProvider, RetrievalResult, TextIndex
from retrieval.sqlite._common import (
    DOCUMENT_COLUMNS,
    aliased_document_columns,
    document_from_row,
    document_rows,
    document_table_statement,
    open_database,
    upsert_document_statement,
)

_DOCUMENTS = "documents"
_EMBEDDINGS = "document_embeddings"


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
        self._connection = open_database(database)
        self._load_extension()

        try:
            self._create_schema()
        except BaseException:
            self._connection.close()
            raise

    async def index(self, documents: Sequence[Document]) -> None:
        items = list(documents)
        if not items:
            return

        rows = document_rows(items)

        embeddings = await self._embedding_provider.embed([document.text for document in items])
        if len(embeddings) != len(items):
            raise ValueError("Embedding provider returned an unexpected number of embeddings")
        self._validate_embeddings(embeddings)

        with self._connection:
            self._connection.executemany(upsert_document_statement(_DOCUMENTS), rows)
            for document, embedding in zip(items, embeddings, strict=True):
                self._connection.execute(
                    f"DELETE FROM {_EMBEDDINGS} WHERE document_id = ?",
                    (document.id,),
                )
                self._connection.execute(
                    f"INSERT INTO {_EMBEDDINGS} (document_id, embedding, parent_key) VALUES (?, ?, ?)",
                    (document.id, sqlite_vec.serialize_float32(embedding), _parent_key(document.parent_id)),
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
        if not self._has_embeddings(parent_id):
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
                FROM {_EMBEDDINGS}
                WHERE embedding MATCH ?
                  AND k = ?
                  {parent_filter}
            )
            SELECT {aliased_document_columns("d")}, matches.distance
            FROM matches
            JOIN {_DOCUMENTS} AS d ON d.id = matches.document_id
            ORDER BY matches.distance
            """,
            parameters,
        ).fetchall()
        return [RetrievalResult(document=document_from_row(row), score=1.0 - row["distance"]) for row in rows]

    async def get(self, document_id: str) -> Document | None:
        row = self._connection.execute(
            f"SELECT {DOCUMENT_COLUMNS} FROM {_DOCUMENTS} WHERE id = ?",
            (document_id,),
        ).fetchone()
        return None if row is None else document_from_row(row)

    async def list_documents(self, *, parent_id: str | None = None, limit: int = 100) -> list[Document]:
        if limit < 1:
            raise ValueError("limit must be at least 1")

        if parent_id is None:
            rows = self._connection.execute(
                f"""
                SELECT {DOCUMENT_COLUMNS} FROM {_DOCUMENTS}
                WHERE parent_id IS NULL
                ORDER BY created_at DESC, id
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        else:
            rows = self._connection.execute(
                f"""
                SELECT {DOCUMENT_COLUMNS} FROM {_DOCUMENTS}
                WHERE parent_id = ?
                ORDER BY created_at, id
                LIMIT ?
                """,
                (parent_id, limit),
            ).fetchall()
        return [document_from_row(row) for row in rows]

    async def delete(self, document_ids: Sequence[str]) -> None:
        ids = [(document_id,) for document_id in dict.fromkeys(document_ids)]
        if not ids:
            return

        with self._connection:
            self._connection.executemany(f"DELETE FROM {_EMBEDDINGS} WHERE document_id = ?", ids)
            self._connection.executemany(f"DELETE FROM {_DOCUMENTS} WHERE id = ?", ids)

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
            self._connection.executescript(document_table_statement(_DOCUMENTS))
            self._connection.execute(
                f"""
                CREATE VIRTUAL TABLE IF NOT EXISTS {_EMBEDDINGS} USING vec0(
                    document_id TEXT PRIMARY KEY,
                    embedding float[{self._dimensions}] distance_metric=cosine,
                    parent_key TEXT
                )
                """
            )
        self._validate_schema_dimensions()

    def _validate_schema_dimensions(self) -> None:
        row = self._connection.execute(
            "SELECT sql FROM sqlite_master WHERE name = ?",
            (_EMBEDDINGS,),
        ).fetchone()
        expected = f"float[{self._dimensions}]"
        if row is None or expected not in row["sql"].casefold():
            raise ValueError(f"The existing {_EMBEDDINGS} table uses different embedding dimensions")

    def _validate_embeddings(self, embeddings: Sequence[Embedding]) -> None:
        if any(len(embedding) != self._dimensions for embedding in embeddings):
            raise ValueError(f"Embedding vectors must have {self._dimensions} dimensions")

    def _has_embeddings(self, parent_id: str | None) -> bool:
        if parent_id is None:
            row = self._connection.execute(f"SELECT EXISTS(SELECT 1 FROM {_EMBEDDINGS})").fetchone()
        else:
            row = self._connection.execute(
                f"SELECT EXISTS(SELECT 1 FROM {_EMBEDDINGS} WHERE parent_key = ?)",
                (_parent_key(parent_id),),
            ).fetchone()
        return bool(row[0])


def _parent_key(parent_id: str | None) -> str:
    return "root" if parent_id is None else f"id:{parent_id}"
