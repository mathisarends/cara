import asyncio
import sqlite3
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

import pytest

from retrieval import Document, Embedding, EmbeddingProvider
from retrieval.sqlite import SQLiteVectorIndex


class FakeEmbeddingProvider(EmbeddingProvider):
    def __init__(self, embeddings: dict[str, Embedding]) -> None:
        self._embeddings = embeddings

    async def embed(self, texts: Sequence[str]) -> list[Embedding]:
        return [self._embeddings[text] for text in texts]


def _index(database: Path, embeddings: dict[str, Embedding]) -> SQLiteVectorIndex:
    return SQLiteVectorIndex(database, FakeEmbeddingProvider(embeddings), dimensions=2)


def test_index_persists_documents_and_vectors(tmp_path: Path) -> None:
    database = tmp_path / "memory.db"
    created_at = datetime(2026, 8, 2, 9, 30, tzinfo=UTC)
    document = Document(
        id="message-1",
        parent_id="conversation-1",
        text="We talked about SQLite.",
        metadata={"role": "user", "turn": 1},
        created_at=created_at,
    )
    index = _index(database, {document.text: [1.0, 0.0]})
    asyncio.run(index.index([document]))
    index.close()

    reopened = _index(database, {"database question": [0.9, 0.1]})
    stored = asyncio.run(reopened.get(document.id))
    results = asyncio.run(reopened.retrieve("database question"))
    reopened.close()

    assert stored == document
    assert results[0].document == document
    assert results[0].score == pytest.approx(0.9939, abs=0.0001)


def test_index_uses_requested_documents_schema(tmp_path: Path) -> None:
    database = tmp_path / "schema.db"
    index = _index(database, {})
    index.close()

    connection = sqlite3.connect(database)
    columns = connection.execute("PRAGMA table_info(documents)").fetchall()
    connection.close()

    assert [(column[1], column[2]) for column in columns] == [
        ("id", "TEXT"),
        ("parent_id", "TEXT"),
        ("text", "TEXT"),
        ("metadata", "TEXT"),
        ("created_at", "TIMESTAMP"),
    ]


def test_index_replaces_content_but_preserves_created_at(tmp_path: Path) -> None:
    database = tmp_path / "replace.db"
    original_time = datetime(2026, 1, 1, tzinfo=UTC)
    index = _index(
        database, {"old": [1.0, 0.0], "new": [0.0, 1.0], "query": [1.0, 0.0]}
    )

    asyncio.run(
        index.index(
            [
                Document(
                    "document", "old", metadata={"version": 1}, created_at=original_time
                )
            ]
        )
    )
    asyncio.run(index.index([Document("document", "new", metadata={"version": 2})]))

    stored = asyncio.run(index.get("document"))
    result = asyncio.run(index.retrieve("query"))[0]
    index.close()

    assert stored is not None
    assert stored.text == "new"
    assert stored.metadata == {"version": 2}
    assert stored.created_at == original_time
    assert result.score == pytest.approx(0.0, abs=0.0001)


def test_list_documents_supports_conversation_hierarchy(tmp_path: Path) -> None:
    database = tmp_path / "hierarchy.db"
    documents = [
        Document(
            "conversation", "SQLite experiment", metadata={"kind": "conversation"}
        ),
        Document(
            "z-message", "Hello", parent_id="conversation", metadata={"role": "user"}
        ),
        Document(
            "a-message", "Hi", parent_id="conversation", metadata={"role": "assistant"}
        ),
    ]
    index = _index(database, {document.text: [1.0, 0.0] for document in documents})
    asyncio.run(index.index(documents))

    roots = asyncio.run(index.list_documents())
    messages = asyncio.run(index.list_documents(parent_id="conversation"))
    index.close()

    assert [document.id for document in roots] == ["conversation"]
    assert [document.id for document in messages] == ["z-message", "a-message"]


def test_search_can_be_limited_to_a_conversation(tmp_path: Path) -> None:
    database = tmp_path / "filter.db"
    documents = [
        Document("first", "first topic", parent_id="conversation-1"),
        Document("second", "second topic", parent_id="conversation-2"),
    ]
    index = _index(
        database,
        {
            "first topic": [1.0, 0.0],
            "second topic": [0.9, 0.1],
            "query": [1.0, 0.0],
        },
    )
    asyncio.run(index.index(documents))

    results = asyncio.run(index.search("query", parent_id="conversation-2"))
    index.close()

    assert [result.document.id for result in results] == ["second"]


def test_delete_removes_document_and_vector(tmp_path: Path) -> None:
    database = tmp_path / "delete.db"
    index = _index(database, {"text": [1.0, 0.0], "query": [1.0, 0.0]})
    asyncio.run(index.index([Document("document", "text")]))

    asyncio.run(index.delete(["document"]))

    assert asyncio.run(index.get("document")) is None
    assert asyncio.run(index.retrieve("query")) == []
    index.close()


def test_index_rejects_non_json_metadata_without_writing(tmp_path: Path) -> None:
    database = tmp_path / "metadata.db"
    index = _index(database, {"text": [1.0, 0.0]})

    with pytest.raises(ValueError, match="JSON-serializable"):
        asyncio.run(
            index.index([Document("document", "text", metadata={"bad": object()})])
        )

    assert asyncio.run(index.get("document")) is None
    index.close()


def test_existing_index_rejects_different_dimensions(tmp_path: Path) -> None:
    database = tmp_path / "dimensions.db"
    index = _index(database, {})
    index.close()

    with pytest.raises(ValueError, match="different embedding dimensions"):
        SQLiteVectorIndex(database, FakeEmbeddingProvider({}), dimensions=3)
