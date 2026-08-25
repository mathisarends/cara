# retrieval

Provider-agnostic indexing and retrieval for Python: chunking, dense
retrieval, lexical retrieval, and rank fusion, behind small abstract base
classes. Core package has **no dependencies**; embedding providers are
optional extras (`pip install "retrieval[openai]"`, `[sqlite]`).

```python
hybrid = ReciprocalRankFusion([vector_index, lexical_index])
results = await hybrid.retrieve("How do I talk to Cara?", limit=5)
```

## Concepts

Four ports — everything else is an implementation of one, and every
implementation is interchangeable:

| Port | Method | Purpose |
| --- | --- | --- |
| `Chunker` | `chunk(text)` | Split a document into indexable pieces. |
| `EmbeddingProvider` | `async embed(texts)` | Text → dense vectors. |
| `LexicalTokenizer` | `tokenize(text)` | Text → matchable terms. |
| `Retriever` / `TextIndex` | `async retrieve(query, *, limit)` (+ `index`/`delete` for `TextIndex`) | Ranked results, optionally writable. |

`Document(id, text, parent_id, metadata, created_at)` and
`RetrievalResult(document, score)` are the shared types. Scores are **not**
comparable across retrievers — rank within one, never threshold across
several.

## Implementations

- **Chunking** — `FixedSizeChunker`, `RecursiveChunker`, `MarkdownChunker`.
  Token-aware via an injectable `TextTokenizer` (default counts code points).
- **Dense** — `InMemoryVectorIndex` (cosine similarity); persistent
  `SQLiteVectorIndex` (`sqlite-vec`) with `list_documents`/`search`/`get`
  scoped by `parent_id`.
- **Lexical** — `InMemoryBM25Index` (Okapi BM25, tunable `k1`/`b`, pluggable
  `LexicalTokenizer` — no stemming/stop-words by default); persistent
  `SQLiteFts5Index` (SQLite FTS5).
- **Caching** — `SQLiteEmbeddingCache` wraps any `EmbeddingProvider` and
  memoizes by a `namespace` + text hash, so re-indexing only pays for new
  text.
- **Fusion** — `ReciprocalRankFusion` combines rankings (not raw scores)
  across any number of `Retriever`s, with per-retriever `weights` and
  over-fetch controls; is itself a `Retriever`, so it nests.
- **Reranking** — `MaximalMarginalRelevance` wraps a `Retriever` and
  diversifies results by penalizing near-duplicates.
- **Embedding providers** — `retrieval.openai.OpenAIEmbeddingProvider`;
  anything else implements `EmbeddingProvider` in one method.

## Scope

Bundled in-memory indexes score linearly (fine into the low tens of
thousands of chunks); not concurrency-safe for writes; no query expansion or
cross-encoder reranking; filtering beyond `parent_id` is left to the caller;
nothing watches files — indexing is the application's job.

## Examples & development

Runnable scripts in [`examples/`](examples). Dev loop:

```bash
uv sync --all-extras
uv run pytest libs/retrieval/tests
uv run ruff check retrieval && uv run ruff format retrieval
```

## Dependencies

None in core. Optional: OpenAI SDK (`[openai]`), `aiosqlite`/`sqlite-vec`
(`[sqlite]`). Not currently wired into `agent` — `agent.tools.actions.memory`
has a disabled placeholder pending a `TextIndex` backend.
