import asyncio
from collections.abc import Sequence

from retrieval import Document, RetrievalResult, Retriever


class ReciprocalRankFusion(Retriever):
    """Merge several retrievers by rank instead of by score.

    Scores from a vector index and a lexical index live on incomparable
    scales, so only their orderings are combined: each retriever
    contributes 1 / (rank_constant + rank) per document.
    """

    def __init__(
        self,
        retrievers: Sequence[Retriever],
        *,
        rank_constant: int = 60,
        candidates_per_retriever: int = 60,
    ) -> None:
        if not retrievers:
            raise ValueError("At least one retriever is required")
        if rank_constant < 1:
            raise ValueError("rank_constant must be at least 1")
        if candidates_per_retriever < 1:
            raise ValueError("candidates_per_retriever must be at least 1")

        self._retrievers = list(retrievers)
        self._rank_constant = rank_constant
        self._candidates_per_retriever = candidates_per_retriever

    async def retrieve(self, query: str, *, limit: int = 5) -> list[RetrievalResult]:
        if limit < 1:
            raise ValueError("limit must be at least 1")

        candidates = max(limit, self._candidates_per_retriever)
        rankings = await asyncio.gather(
            *(retriever.retrieve(query, limit=candidates) for retriever in self._retrievers)
        )

        documents: dict[str, Document] = {}
        scores: dict[str, float] = {}
        for ranking in rankings:
            for rank, result in enumerate(ranking, start=1):
                documents[result.document.id] = result.document
                scores[result.document.id] = scores.get(result.document.id, 0.0) + 1 / (self._rank_constant + rank)

        results = [
            RetrievalResult(document=documents[document_id], score=score) for document_id, score in scores.items()
        ]
        return sorted(results, key=lambda result: result.score, reverse=True)[:limit]
