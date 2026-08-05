from collections.abc import Sequence
from datetime import UTC, date, datetime, time
from pathlib import Path

from cara.memory._config import EMBEDDING_DIMENSIONS, EMBEDDING_MODEL, cache_namespace
from retrieval import Document, EmbeddingProvider
from retrieval.chunking import MarkdownChunker
from retrieval.openai import OpenAIEmbeddingProvider
from retrieval.sqlite import SQLiteEmbeddingCache, SQLiteFts5Index, SQLiteVectorIndex


async def index_memory_directory(
    directory: Path,
    database: Path,
    *,
    embedding_provider: EmbeddingProvider | None = None,
    dataset: str | None = None,
    dimensions: int = EMBEDDING_DIMENSIONS,
) -> int:
    """Chunk Markdown memory files and index them through both SQLite indexes."""
    documents = memory_documents(directory, dataset=dataset)
    database.parent.mkdir(parents=True, exist_ok=True)
    provider = embedding_provider or OpenAIEmbeddingProvider(EMBEDDING_MODEL)
    cache = SQLiteEmbeddingCache(
        database,
        provider,
        namespace=cache_namespace(dimensions, dataset),
    )
    vector = SQLiteVectorIndex(database, cache, dimensions=dimensions)
    lexical = SQLiteFts5Index(database)
    try:
        await vector.index(documents)
        await lexical.index(documents)
    finally:
        await vector.close()
        await lexical.close()
        await cache.close()
    return len(documents)


async def delete_memory_dataset(
    database: Path,
    directory: Path,
    *,
    dataset: str,
    dimensions: int = EMBEDDING_DIMENSIONS,
) -> int:
    """Delete the documents represented by a mock source directory."""
    if not database.exists():
        return 0
    documents = memory_documents(directory, dataset=dataset)
    ids = [document.id for document in documents]
    lexical = SQLiteFts5Index(database)
    cache = SQLiteEmbeddingCache(
        database,
        _DeletionOnlyEmbeddingProvider(),
        namespace=cache_namespace(dimensions, dataset),
    )
    vector = SQLiteVectorIndex(database, cache, dimensions=dimensions)
    try:
        await lexical.delete(ids)
        await vector.delete(ids)
        await cache.delete([document.text for document in documents])
    finally:
        await vector.close()
        await lexical.close()
        await cache.close()
    return len(ids)


def memory_documents(directory: Path, *, dataset: str | None = None) -> list[Document]:
    chunker = MarkdownChunker(chunk_size=400, chunk_overlap=40)
    paths = [directory / "MEMORY.md", *sorted((directory / "daily").glob("*.md"))]
    return [
        document
        for path in paths
        if path.is_file()
        for document in _chunk_memory_file(path, directory, chunker, dataset)
    ]


def _chunk_memory_file(
    path: Path,
    root: Path,
    chunker: MarkdownChunker,
    dataset: str | None,
) -> list[Document]:
    relative_path = path.relative_to(root).as_posix()
    source_id = relative_path.removesuffix(".md")
    prefix = f"{dataset}:" if dataset else ""
    parent_id = f"{prefix}{source_id}"
    text = path.read_text(encoding="utf-8")
    created_at = _created_at(path)
    metadata: dict[str, object] = {"path": relative_path, "source": "memory"}
    if dataset is not None:
        metadata["dataset"] = dataset
    parent = Document(
        id=parent_id,
        text=text,
        metadata=metadata,
        created_at=created_at,
    )
    chunks = [
        Document(
            id=f"{parent_id}:{number}",
            parent_id=parent_id,
            text=chunk,
            metadata={**metadata, "chunk": number},
            created_at=created_at,
        )
        for number, chunk in enumerate(chunker.chunk(text), start=1)
    ]
    return [parent, *chunks]


def _created_at(path: Path) -> datetime:
    if path.parent.name == "daily":
        try:
            return datetime.combine(date.fromisoformat(path.stem), time.min, tzinfo=UTC)
        except ValueError:
            pass
    return datetime.fromtimestamp(path.stat().st_mtime, UTC)


class _DeletionOnlyEmbeddingProvider(EmbeddingProvider):
    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        del texts
        raise RuntimeError("The deletion-only embedding provider cannot embed text")
