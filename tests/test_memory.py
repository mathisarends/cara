import asyncio
import json
import sqlite3
from collections.abc import Sequence
from pathlib import Path

import sqlite_vec

from cara.memory import HybridMemorySearch, delete_memory_dataset, index_memory_directory
from cara.tools import create_tool_context, create_tools
from retrieval import Embedding, EmbeddingProvider


class KeywordEmbeddingProvider(EmbeddingProvider):
    async def embed(self, texts: Sequence[str]) -> list[Embedding]:
        return [
            [
                float("tank" in text.casefold() or "wasser" in text.casefold()),
                float("sqlite" in text.casefold()),
                1.0,
            ]
            for text in texts
        ]


def _write_memory(root: Path) -> None:
    (root / "daily").mkdir(parents=True)
    (root / "MEMORY.md").write_text(
        "# Dauerhaft\n\nRegenwasser wird im Tank gesammelt.\n",
        encoding="utf-8",
    )
    (root / "daily" / "2026-08-01.md").write_text(
        "# Entwicklung\n\nSQLite speichert die Chunks dauerhaft.\n",
        encoding="utf-8",
    )


def test_seed_search_and_delete_mock_memory(tmp_path: Path) -> None:
    source = tmp_path / "memory"
    database = tmp_path / "memory.db"
    _write_memory(source)
    provider = KeywordEmbeddingProvider()

    indexed = asyncio.run(
        index_memory_directory(
            source,
            database,
            embedding_provider=provider,
            dataset="test-mock",
            dimensions=3,
        )
    )
    search = HybridMemorySearch(database, embedding_provider=provider, dimensions=3)
    results = asyncio.run(search.search("Wassertank", limit=2))

    assert indexed == 4
    assert results[0].document.id.startswith("test-mock:MEMORY")
    assert results[0].vector_score > 0
    assert results[0].text_score == 0
    assert results[0].score == 0.7 * results[0].vector_score

    deleted = asyncio.run(delete_memory_dataset(database, source, dataset="test-mock", dimensions=3))

    assert deleted == indexed
    with sqlite3.connect(database) as connection:
        connection.enable_load_extension(True)
        sqlite_vec.load(connection)
        connection.enable_load_extension(False)
        assert connection.execute("SELECT count(*) FROM documents").fetchone() == (0,)
        assert connection.execute("SELECT count(*) FROM document_embeddings").fetchone() == (0,)
        assert connection.execute(
            "SELECT count(*) FROM embedding_cache WHERE namespace LIKE '%:test-mock'"
        ).fetchone() == (0,)


def test_search_memory_tool_returns_hybrid_result_shape(tmp_path: Path) -> None:
    source = tmp_path / "memory"
    database = tmp_path / "memory.db"
    _write_memory(source)
    provider = KeywordEmbeddingProvider()
    asyncio.run(
        index_memory_directory(
            source,
            database,
            embedding_provider=provider,
            dimensions=3,
        )
    )
    tools = create_tools(create_tool_context(HybridMemorySearch(database, embedding_provider=provider, dimensions=3)))

    response = asyncio.run(tools.execute("search_memory", {"query": "SQLite", "limit": 1}))
    payload = json.loads(response.result)

    assert response.ok
    assert set(payload[0]) == {
        "id",
        "parentId",
        "text",
        "metadata",
        "createdAt",
        "vectorScore",
        "textScore",
        "score",
    }
    assert payload[0]["textScore"] > 0
