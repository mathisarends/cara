from dataclasses import dataclass

type Embedding = list[float]


@dataclass(frozen=True, slots=True)
class Document:
    id: str
    text: str


@dataclass(frozen=True, slots=True)
class RetrievalResult:
    document: Document
    score: float
