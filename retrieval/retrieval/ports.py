from abc import ABC, abstractmethod
from collections.abc import Sequence

from retrieval.types import Document, Embedding, RetrievalResult


class EmbeddingProvider(ABC):
    @abstractmethod
    async def embed(self, texts: Sequence[str]) -> list[Embedding]:
        raise NotImplementedError


class Retriever(ABC):
    @abstractmethod
    async def retrieve(self, query: str, *, limit: int = 5) -> list[RetrievalResult]:
        raise NotImplementedError


class TextIndex(Retriever):
    @abstractmethod
    async def index(self, documents: Sequence[Document]) -> None:
        raise NotImplementedError
