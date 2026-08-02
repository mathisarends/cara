import asyncio

import pytest

from retrieval import Document, RetrievalResult, Retriever
from retrieval.fusion import ReciprocalRankFusion


class FakeRetriever(Retriever):
    def __init__(self, results: list[RetrievalResult]) -> None:
        self._results = results
        self.requested_limit: int | None = None

    async def retrieve(self, query: str, *, limit: int = 5) -> list[RetrievalResult]:
        self.requested_limit = limit
        return self._results[:limit]


def _result(document_id: str, score: float) -> RetrievalResult:
    return RetrievalResult(document=Document(id=document_id, text=document_id), score=score)


def test_retrieve_prefers_documents_ranked_well_by_every_retriever() -> None:
    dense = FakeRetriever([_result("shared", 0.9), _result("dense-only", 0.8)])
    lexical = FakeRetriever([_result("lexical-only", 42.0), _result("shared", 12.0)])
    fusion = ReciprocalRankFusion([dense, lexical])

    results = asyncio.run(fusion.retrieve("query"))

    assert results[0].document.id == "shared"
    assert len(results) == 3


def test_retrieve_ignores_incomparable_score_scales() -> None:
    dense = FakeRetriever([_result("dense-only", 0.51), _result("shared", 0.5)])
    lexical = FakeRetriever([_result("shared", 99.0)])
    fusion = ReciprocalRankFusion([dense, lexical])

    results = asyncio.run(fusion.retrieve("query"))

    assert [result.document.id for result in results] == ["shared", "dense-only"]


def test_retrieve_requests_more_candidates_than_it_returns() -> None:
    retriever = FakeRetriever([_result("only", 1.0)])
    fusion = ReciprocalRankFusion([retriever], candidates_per_retriever=30)

    asyncio.run(fusion.retrieve("query", limit=2))

    assert retriever.requested_limit == 30


def test_retrieve_honours_a_limit_above_the_candidate_depth() -> None:
    retriever = FakeRetriever([_result("first", 1.0), _result("second", 0.5)])
    fusion = ReciprocalRankFusion([retriever], candidates_per_retriever=1)

    results = asyncio.run(fusion.retrieve("query", limit=2))

    assert retriever.requested_limit == 2
    assert len(results) == 2


def test_retrieve_rejects_non_positive_limit() -> None:
    fusion = ReciprocalRankFusion([FakeRetriever([])])

    with pytest.raises(ValueError, match="limit must be at least 1"):
        asyncio.run(fusion.retrieve("query", limit=0))


def test_fusion_requires_at_least_one_retriever() -> None:
    with pytest.raises(ValueError, match="At least one retriever is required"):
        ReciprocalRankFusion([])
