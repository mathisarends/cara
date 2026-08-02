import asyncio
import sqlite3
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

import sqlite_vec

from cara.memory import HybridMemoryResult, HybridMemorySearch, delete_memory_dataset, index_memory_directory
from cara.tools import create_tool_context, create_tools
from cara.tools.catalog import _render_memory_results
from retrieval import Document, Embedding, EmbeddingProvider


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


def test_search_memory_returns_chunks_instead_of_parent_documents(tmp_path: Path) -> None:
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
    search = HybridMemorySearch(database, embedding_provider=provider, dimensions=3)

    results = asyncio.run(search.search("SQLite", limit=1))

    assert len(results) == 1
    assert results[0].document.parent_id == "daily/2026-08-01"


def test_search_memory_tool_returns_concise_source_attributed_excerpts(tmp_path: Path) -> None:
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

    assert response.ok
    assert isinstance(response.result, str)
    assert response.result == (
        "Memory excerpts, ordered by relevance:\n\n"
        "[daily/2026-08-01.md | 2026-08-01]\n"
        "# Entwicklung\n\nSQLite speichert die Chunks dauerhaft."
    )
    assert "Score" not in response.result
    assert "parentId" not in response.result


def test_memory_tool_output_groups_excerpts_from_the_same_source() -> None:
    created_at = datetime(2026, 8, 1, tzinfo=UTC)
    results = [
        HybridMemoryResult(
            document=Document(
                id=f"daily/2026-08-01:{chunk}",
                parent_id="daily/2026-08-01",
                text=text,
                metadata={"path": "daily/2026-08-01.md"},
                created_at=created_at,
            ),
            vector_score=vector_score,
            text_score=0.0,
            score=vector_score * 0.7,
        )
        for chunk, text, vector_score in (
            (1, "# Entscheidung\n\nDaily Notes sind Parent-Dokumente.", 0.9),
            (2, "# Umsetzung\n\nAbschnitte verweisen mit parent_id darauf.", 0.8),
        )
    ]

    rendered = _render_memory_results(results)

    assert rendered.count("[daily/2026-08-01.md | 2026-08-01]") == 1
    assert "Daily Notes sind Parent-Dokumente." in rendered
    assert "Abschnitte verweisen mit parent_id darauf." in rendered
    assert "0.9" not in rendered
