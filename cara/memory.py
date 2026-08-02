import asyncio
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from pathlib import Path

from retrieval import Document, EmbeddingProvider, RetrievalResult
from retrieval.chunking import MarkdownChunker
from retrieval.openai import OpenAIEmbeddingProvider
from retrieval.sqlite import SQLiteEmbeddingCache, SQLiteFts5Index, SQLiteVectorIndex

DEFAULT_MEMORY_DATABASE = Path("temp/cara-memory.db")
DEFAULT_MEMORY_SOURCE = Path(__file__).parent / "prompt" / "content"
EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIMENSIONS = 1536
_CANDIDATE_MULTIPLIER = 4
_MINIMUM_CANDIDATES = 20
_SIGNIFICANT_SCORE_DROP_RATIO = 0.5


@dataclass(frozen=True, slots=True)
class HybridMemoryResult:
    document: Document
    vector_score: float
    text_score: float
    score: float


class HybridMemorySearch:
    """Search a persisted memory corpus with weighted vector and FTS scores."""

    def __init__(
        self,
        database: Path = DEFAULT_MEMORY_DATABASE,
        *,
        embedding_provider: EmbeddingProvider | None = None,
        dimensions: int = EMBEDDING_DIMENSIONS,
    ) -> None:
        self._database = database
        self._embedding_provider = embedding_provider
        self._dimensions = dimensions

    async def search(
        self,
        query: str,
        *,
        limit: int = 5,
        vector_weight: float = 0.7,
        text_weight: float = 0.3,
    ) -> list[HybridMemoryResult]:
        if limit < 1:
            raise ValueError("limit must be at least 1")
        if vector_weight < 0 or text_weight < 0:
            raise ValueError("weights must not be negative")
        if vector_weight == 0 and text_weight == 0:
            raise ValueError("at least one weight must be positive")
        if not self._database.exists():
            return []

        cache, vector, lexical = self._open_indexes()
        candidates = max(limit * _CANDIDATE_MULTIPLIER, _MINIMUM_CANDIDATES)
        try:
            vector_results, text_results = await asyncio.gather(
                vector.retrieve(query, limit=candidates),
                lexical.retrieve(query, limit=candidates),
            )
            results = _merge_results(
                vector_results,
                text_results,
                vector_weight=vector_weight,
                text_weight=text_weight,
            )
            return _select_memory_chunks(results, limit=limit)
        finally:
            await vector.close()
            await lexical.close()
            await cache.close()

    def _open_indexes(
        self,
    ) -> tuple[SQLiteEmbeddingCache, SQLiteVectorIndex, SQLiteFts5Index]:
        provider = self._embedding_provider or OpenAIEmbeddingProvider(EMBEDDING_MODEL)
        cache = SQLiteEmbeddingCache(
            self._database,
            provider,
            namespace=_cache_namespace(self._dimensions),
        )
        return (
            cache,
            SQLiteVectorIndex(self._database, cache, dimensions=self._dimensions),
            SQLiteFts5Index(self._database),
        )


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
        namespace=_cache_namespace(dimensions, dataset),
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
        namespace=_cache_namespace(dimensions, dataset),
    )
    vector = SQLiteVectorIndex(
        database,
        cache,
        dimensions=dimensions,
    )
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


def _cache_namespace(dimensions: int, dataset: str | None = None) -> str:
    base = f"{EMBEDDING_MODEL}:{dimensions}"
    return base if dataset is None else f"{base}:{dataset}"


def _merge_results(
    vector: Sequence[RetrievalResult],
    keyword: Sequence[RetrievalResult],
    *,
    vector_weight: float,
    text_weight: float,
) -> list[HybridMemoryResult]:
    by_id: dict[str, tuple[Document, float, float]] = {}
    for result in vector:
        by_id[result.document.id] = (result.document, result.score, 0.0)
    for result in keyword:
        existing = by_id.get(result.document.id)
        vector_score = 0.0 if existing is None else existing[1]
        by_id[result.document.id] = (result.document, vector_score, result.score)

    merged = [
        HybridMemoryResult(
            document=document,
            vector_score=vector_score,
            text_score=text_score,
            score=vector_weight * vector_score + text_weight * text_score,
        )
        for document, vector_score, text_score in by_id.values()
    ]
    return sorted(merged, key=lambda result: result.score, reverse=True)


def _select_memory_chunks(
    results: Sequence[HybridMemoryResult],
    *,
    limit: int,
) -> list[HybridMemoryResult]:
    chunks = [result for result in results if result.document.parent_id is not None]
    candidates = chunks or list(results)
    if not candidates:
        return []

    selected = [candidates[0]]
    for candidate in candidates[1:limit]:
        previous_score = selected[-1].score
        if previous_score > 0 and candidate.score < previous_score * _SIGNIFICANT_SCORE_DROP_RATIO:
            break
        selected.append(candidate)
    return selected


class _DeletionOnlyEmbeddingProvider(EmbeddingProvider):
    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        del texts
        raise RuntimeError("The deletion-only embedding provider cannot embed text")
