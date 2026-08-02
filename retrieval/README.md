# retrieval

Provider-agnostic indexing and retrieval for Python.

`retrieval` gives you the building blocks of a RAG pipeline — chunking, dense
retrieval, lexical retrieval and rank fusion — behind small abstract base
classes you can implement yourself. The core package has **no dependencies**;
embedding providers are optional extras.

```python
hybrid = ReciprocalRankFusion([vector_index, lexical_index])
results = await hybrid.retrieve("How do I talk to Cara?", limit=5)
```

---

## Table of contents

- [Installation](#installation)
- [Quickstart](#quickstart)
- [Concepts](#concepts)
  - [Ports](#ports)
  - [Types](#types)
- [Chunking](#chunking)
  - [Strategies](#strategies)
  - [Token-aware sizing](#token-aware-sizing)
- [Dense retrieval](#dense-retrieval)
- [Lexical retrieval](#lexical-retrieval)
  - [BM25 parameters](#bm25-parameters)
  - [Tokenization, stemming and stop words](#tokenization-stemming-and-stop-words)
- [Hybrid retrieval](#hybrid-retrieval)
- [Embedding providers](#embedding-providers)
  - [OpenAI](#openai)
  - [Writing your own](#writing-your-own)
- [Extending the package](#extending-the-package)
- [Scope and limitations](#scope-and-limitations)
- [Examples](#examples)
- [Development](#development)

---

## Installation

```bash
pip install retrieval
```

The core package pulls in nothing. Install an extra if you want a bundled
embedding provider:

```bash
pip install "retrieval[openai]"
```

Requires Python 3.13.

---

## Quickstart

```python
import asyncio

from retrieval import Document
from retrieval.chunking import MarkdownChunker
from retrieval.lexical import InMemoryBM25Index


async def main() -> None:
    source = Document(id="cara", text=open("docs/cara.md").read())

    chunker = MarkdownChunker(chunk_size=500, chunk_overlap=50)
    chunks = [
        Document(id=f"{source.id}:{number}", text=text)
        for number, text in enumerate(chunker.chunk(source.text), start=1)
    ]

    index = InMemoryBM25Index()
    await index.index(chunks)

    for result in await index.retrieve("wake word detection", limit=3):
        print(f"{result.score:.3f}  {result.document.text[:60]}")


asyncio.run(main())
```

`InMemoryBM25Index` needs no API key and no model — it is the fastest way to
get a working retrieval loop before you decide on an embedding provider.

---

## Concepts

The package is built around four abstract base classes. Everything else is an
implementation of one of them, and every implementation is interchangeable.

### Ports

```python
from retrieval import Chunker, EmbeddingProvider, LexicalTokenizer, Retriever, TextIndex
```

| Port | Method | Purpose |
| --- | --- | --- |
| `Chunker` | `chunk(text) -> list[str]` | Split a document into indexable pieces. |
| `EmbeddingProvider` | `async embed(texts) -> list[Embedding]` | Turn text into dense vectors. |
| `LexicalTokenizer` | `tokenize(text) -> list[str]` | Split text into the terms a lexical index matches on. |
| `Retriever` | `async retrieve(query, *, limit) -> list[RetrievalResult]` | Anything that answers a query with ranked documents. |
| `TextIndex` | `Retriever` + `async index(documents)` | A retriever you can also write to. |

`TextIndex` extends `Retriever`, so an index and a fusion layer are the same
kind of thing to a caller. That is what makes [hybrid
retrieval](#hybrid-retrieval) composable.

### Types

```python
from retrieval import Document, Embedding, RetrievalResult
```

```python
Embedding = list[float]

@dataclass(frozen=True, slots=True)
class Document:
    id: str
    text: str

@dataclass(frozen=True, slots=True)
class RetrievalResult:
    document: Document
    score: float
```

`Document.id` is the identity used for deduplication: re-indexing an existing
id replaces the document in every index, and fusion merges results by id.

Scores are **not comparable across retrievers.** Cosine similarity lands
around `0.9`, BM25 around `12`, reciprocal rank fusion around `0.03`. Use them
to rank within one retriever, never to threshold across several.

---

## Chunking

```python
from retrieval.chunking import FixedSizeChunker, MarkdownChunker, RecursiveChunker
```

### Strategies

| Chunker | Behaviour | Use when |
| --- | --- | --- |
| `FixedSizeChunker` | Hard token windows with optional overlap. | Content has no structure worth preserving. |
| `RecursiveChunker` | Splits on the first separator that fits — paragraph, line, sentence, word — then falls back to a hard boundary. | General prose. |
| `MarkdownChunker` | Keeps Markdown sections intact, recursively splitting oversized ones. Heading-like lines inside fenced code blocks do not start a new section. | Docs, READMEs, wikis. |

```python
chunker = RecursiveChunker(chunk_size=500, chunk_overlap=50)
chunks = chunker.chunk(text)
```

`RecursiveChunker` accepts custom separators, applied in order:

```python
RecursiveChunker(500, chunk_overlap=50, separators=("\n\n", "\n", "; ", " "))
```

### Token-aware sizing

`chunk_size` is measured in *tokens*, and a token is whatever the injected
tokenizer says it is. The default `CharacterTokenizer` counts Unicode code
points, which keeps the core dependency-free.

To size chunks by real model tokens, pass any object implementing
`TextTokenizer`:

```python
from collections.abc import Sequence

import tiktoken

from retrieval.chunking import RecursiveChunker, TextTokenizer


class TiktokenTokenizer(TextTokenizer):
    def __init__(self, encoding: str = "cl100k_base") -> None:
        self._encoding = tiktoken.get_encoding(encoding)

    def encode(self, text: str) -> Sequence[int]:
        return self._encoding.encode(text)

    def decode(self, tokens: Sequence[int]) -> str:
        return self._encoding.decode(list(tokens))


chunker = RecursiveChunker(500, chunk_overlap=50, tokenizer=TiktokenTokenizer())
```

---

## Dense retrieval

```python
from retrieval.vector import InMemoryVectorIndex
```

`InMemoryVectorIndex` embeds documents on `index()` and ranks by cosine
similarity. Vectors are normalized on write, so retrieval is a dot product.

```python
index = InMemoryVectorIndex(embedding_provider)
await index.index(documents)

results = await index.retrieve("how does the assistant listen?", limit=5)
```

Dense retrieval matches *meaning*: it finds the paraphrase that shares no
words with the query. It fails on terms the embedding model never saw —
product names, identifiers, error codes, version numbers. That is exactly what
[lexical retrieval](#lexical-retrieval) is good at.

All documents in an index must share one embedding dimensionality;
`index()` raises `ValueError` otherwise.

---

## Lexical retrieval

```python
from retrieval.lexical import InMemoryBM25Index, WordTokenizer
```

`InMemoryBM25Index` implements Okapi BM25 with Lucene's inverse document
frequency. It matches exact terms, needs no model, no API key and no network.

```python
index = InMemoryBM25Index()
await index.index(documents)

results = await index.retrieve("wakewordkit", limit=5)
```

Documents that share no term with the query are omitted rather than returned
with a zero score — this keeps irrelevant documents out of the rankings that
[fusion](#hybrid-retrieval) consumes.

Document frequencies are maintained incrementally, so re-indexing a document
under an existing id correctly retires the terms of the previous version.

### BM25 parameters

```python
InMemoryBM25Index(k1=1.5, b=0.75)
```

| Parameter | Default | Effect |
| --- | --- | --- |
| `k1` | `1.5` | Term-frequency saturation. Lower means repeated terms stop helping sooner. `0` reduces scoring to presence/absence. |
| `b` | `0.75` | Length normalization, from `0` (ignore document length) to `1` (fully normalize). Lower it when your chunks vary wildly in length for legitimate reasons. |

The defaults are the standard ones and are a reasonable starting point for
most corpora. Tune them against a labelled query set, not by intuition.

### Tokenization, stemming and stop words

BM25 matches terms literally, so the tokenizer decides what counts as a match.
The default `WordTokenizer` splits on Unicode word boundaries and case-folds:

```python
WordTokenizer().tokenize("Grüße, Welt! 42")
# ['grüsse', 'welt', '42']
```

It deliberately does **no stemming and removes no stop words.** Both are
language-specific, and shipping a German or English word list in a
general-purpose package would silently degrade every other language. Instead,
they are a one-method extension point — implement `LexicalTokenizer` and pass
it in (this example needs `pip install snowballstemmer`):

```python
import re

import snowballstemmer

from retrieval import LexicalTokenizer

STOP_WORDS = {"der", "die", "das", "und", "ist", "ein", "eine"}


class GermanTokenizer(LexicalTokenizer):
    """Case-folded word tokens, stop-word filtered and Snowball-stemmed."""

    _WORDS = re.compile(r"\w+", re.UNICODE)

    def __init__(self) -> None:
        self._stemmer = snowballstemmer.stemmer("german")

    def tokenize(self, text: str) -> list[str]:
        words = self._WORDS.findall(text.casefold())
        return [self._stemmer.stemWord(word) for word in words if word not in STOP_WORDS]


index = InMemoryBM25Index(GermanTokenizer())
```

With stemming, a query for `Spracherkennung` matches a document containing
`Spracherkennungen`; without it, the two are unrelated terms.

Use the **same tokenizer for indexing and querying.** The index applies its
tokenizer to both, so this holds automatically — but if you swap the tokenizer
on a populated index, re-index everything.

---

## Hybrid retrieval

```python
from retrieval.fusion import ReciprocalRankFusion
```

Dense and lexical retrieval fail in different places, which makes them worth
combining. Their scores are not comparable, so `ReciprocalRankFusion` combines
their *rankings* instead: each retriever contributes `1 / (rank_constant + rank)`
per document, and the sums are re-sorted.

```python
hybrid = ReciprocalRankFusion([vector_index, lexical_index])
results = await hybrid.retrieve("wakewordkit setup", limit=5)
```

`ReciprocalRankFusion` is itself a `Retriever`, so it accepts any mix of
indexes, remote services and other fusions — and can be nested.

Retrievers are queried concurrently via `asyncio.gather`.

| Parameter | Default | Effect |
| --- | --- | --- |
| `rank_constant` | `60` | Dampens the influence of top ranks. The standard value from the original RRF paper. Lower values make rank 1 dominate. |
| `candidates_per_retriever` | `60` | How many results to request from each retriever. Depth matters: a document ranked 40th by both retrievers can only outrank a one-sided winner if both lists reach that far. |

A document found by one retriever still surfaces — fusion rewards agreement
without requiring it.

---

## Embedding providers

### OpenAI

Install the extra, then:

```python
from retrieval.openai import OpenAICredentials, OpenAIEmbeddingModel, OpenAIEmbeddingProvider

provider = OpenAIEmbeddingProvider(
    OpenAIEmbeddingModel.TEXT_EMBEDDING_3_SMALL,
    credentials=OpenAICredentials(),
)
```

`OpenAICredentials` reads `OPENAI_API_KEY` from the environment or a `.env`
file. Pass the key explicitly if you manage secrets elsewhere:

```python
OpenAICredentials(api_key="sk-...")
```

The model argument accepts the `OpenAIEmbeddingModel` enum or any model id as
a plain string, so new models work before the enum catches up. Shorten vectors
with `dimensions=` where the model supports it:

```python
OpenAIEmbeddingProvider(
    OpenAIEmbeddingModel.TEXT_EMBEDDING_3_LARGE,
    credentials=OpenAICredentials(),
    dimensions=512,
)
```

Pass `client=` to reuse a configured `AsyncOpenAI` instance — for Azure,
a proxy, or custom retry and timeout settings.

### Writing your own

Any embedding model fits behind one method. The provider must return one
vector per input, in input order:

```python
from collections.abc import Sequence

from retrieval import Embedding, EmbeddingProvider


class SentenceTransformerProvider(EmbeddingProvider):
    def __init__(self, model_name: str = "all-MiniLM-L6-v2") -> None:
        from sentence_transformers import SentenceTransformer

        self._model = SentenceTransformer(model_name)

    async def embed(self, texts: Sequence[str]) -> list[Embedding]:
        return self._model.encode(list(texts)).tolist()
```

---

## Extending the package

Every part of the pipeline is replaceable through the port it implements:

- **A vector database** — implement `TextIndex` over Qdrant, pgvector or
  Elasticsearch. It drops straight into `ReciprocalRankFusion` next to the
  in-memory indexes.
- **A reranker** — implement `Retriever`, wrap another retriever, over-fetch
  and re-sort. Callers cannot tell the difference.
- **A remote search API** — implement `Retriever` and it becomes fusible with
  your local indexes.
- **A chunker** — implement `Chunker` for code-aware, semantic or
  layout-aware splitting.

```python
from retrieval import RetrievalResult, Retriever


class CrossEncoderReranker(Retriever):
    def __init__(self, retriever: Retriever, *, candidates: int = 50) -> None:
        self._retriever = retriever
        self._candidates = candidates

    async def retrieve(self, query: str, *, limit: int = 5) -> list[RetrievalResult]:
        results = await self._retriever.retrieve(query, limit=self._candidates)
        return _rerank(query, results)[:limit]
```

---

## Scope and limitations

Be deliberate about what this package is:

- **The bundled indexes are in-memory and non-persistent.** State lives in the
  process and is lost on restart.
- **They score linearly over every document.** `InMemoryBM25Index` has no
  inverted-index posting lists, and `InMemoryVectorIndex` has no ANN structure.
  Both are fine into the low tens of thousands of chunks and are the wrong tool
  above that — move to a real store behind the same `TextIndex` port.
- **Neither is concurrency-safe.** Serialize writes yourself if you index from
  multiple tasks.
- **No query expansion, no reranking, no metadata filtering** is included.
  `Document` carries an id and text, nothing else.

The ports are the stable part; the in-memory implementations are reference
implementations that keep the package honest and dependency-free.

---

## Examples

Runnable scripts live in [`examples/`](examples):

| Script | Shows |
| --- | --- |
| `chunking_strategies.py` | All three chunkers on the same input, plus the tokenizer API. |
| `index_and_retrieve.py` | Chunk, embed and query with the OpenAI provider. |
| `hybrid_retrieval.py` | Vector and BM25 indexes merged with reciprocal rank fusion. |

The last two need `OPENAI_API_KEY`.

---

## Development

```bash
uv sync
uv run pytest retrieval/tests
uv run ruff check retrieval
uv run ruff format retrieval
```
