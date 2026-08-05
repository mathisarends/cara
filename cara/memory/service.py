import asyncio
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from cara.memory._config import (
    DEFAULT_MEMORY_DATABASE,
    EMBEDDING_DIMENSIONS,
    EMBEDDING_MODEL,
    cache_namespace,
)
from retrieval import Document, EmbeddingProvider, RetrievalResult
from retrieval.openai import OpenAIEmbeddingProvider
from retrieval.sqlite import SQLiteEmbeddingCache, SQLiteFts5Index, SQLiteVectorIndex

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
            namespace=cache_namespace(self._dimensions),
        )
        return (
            cache,
            SQLiteVectorIndex(self._database, cache, dimensions=self._dimensions),
            SQLiteFts5Index(self._database),
        )


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
