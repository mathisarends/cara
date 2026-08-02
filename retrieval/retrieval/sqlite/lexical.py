import re
from collections.abc import Sequence
from pathlib import Path
from types import TracebackType

from retrieval import Document, RetrievalResult, TextIndex
from retrieval.sqlite._common import (
    DOCUMENT_COLUMNS,
    aliased_document_columns,
    document_from_row,
    document_rows,
    document_table_statement,
    open_database,
    upsert_document_statement,
)

_DOCUMENTS = "lexical_documents"
_SEARCH = "lexical_documents_fts"
_QUERY_TERMS = re.compile(r"\w+", re.UNICODE)


class SQLiteFts5Index(TextIndex):
    """Persistent BM25 index backed by SQLite's FTS5 extension.

    Terms are matched by FTS5 rather than by a LexicalTokenizer: the
    tokenizer runs inside SQLite, so it is configured with an FTS5
    tokenizer specification instead of a Python object.
    """

    def __init__(self, database: str | Path, *, tokenizer: str = "unicode61 remove_diacritics 2") -> None:
        self._connection = open_database(database)
        self._tokenizer = tokenizer

        try:
            self._create_schema()
        except BaseException:
            self._connection.close()
            raise

    async def index(self, documents: Sequence[Document]) -> None:
        items = list(documents)
        if not items:
            return

        rows = document_rows(items)
        with self._connection:
            self._connection.executemany(upsert_document_statement(_DOCUMENTS), rows)

    async def retrieve(self, query: str, *, limit: int = 5) -> list[RetrievalResult]:
        return await self.search(query, limit=limit)

    async def search(
        self,
        query: str,
        *,
        limit: int = 5,
        parent_id: str | None = None,
    ) -> list[RetrievalResult]:
        if limit < 1:
            raise ValueError("limit must be at least 1")

        match_expression = _match_expression(query)
        if match_expression is None:
            return []

        parameters: list[object] = [match_expression]
        parent_filter = ""
        if parent_id is not None:
            parent_filter = "AND d.parent_id = ?"
            parameters.append(parent_id)
        parameters.append(limit)

        rows = self._connection.execute(
            f"""
            SELECT {aliased_document_columns("d")}, bm25({_SEARCH}) AS relevance
            FROM {_SEARCH}
            JOIN {_DOCUMENTS} AS d ON d.rowid = {_SEARCH}.rowid
            WHERE {_SEARCH} MATCH ?
              {parent_filter}
            ORDER BY relevance
            LIMIT ?
            """,
            parameters,
        ).fetchall()
        return [RetrievalResult(document=document_from_row(row), score=-row["relevance"]) for row in rows]

    async def get(self, document_id: str) -> Document | None:
        row = self._connection.execute(
            f"SELECT {DOCUMENT_COLUMNS} FROM {_DOCUMENTS} WHERE id = ?",
            (document_id,),
        ).fetchone()
        return None if row is None else document_from_row(row)

    async def delete(self, document_ids: Sequence[str]) -> None:
        ids = [(document_id,) for document_id in dict.fromkeys(document_ids)]
        if not ids:
            return

        with self._connection:
            self._connection.executemany(f"DELETE FROM {_DOCUMENTS} WHERE id = ?", ids)

    def close(self) -> None:
        self._connection.close()

    def __enter__(self) -> "SQLiteFts5Index":
        return self

    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    def _create_schema(self) -> None:
        with self._connection:
            self._connection.executescript(document_table_statement(_DOCUMENTS))
            self._connection.execute(
                f"""
                CREATE VIRTUAL TABLE IF NOT EXISTS {_SEARCH} USING fts5(
                    text,
                    content={_DOCUMENTS},
                    content_rowid=rowid,
                    tokenize='{self._tokenizer}'
                )
                """
            )
            self._connection.executescript(_synchronization_triggers())


def _match_expression(query: str) -> str | None:
    """Turn a user query into an FTS5 OR expression over its bare terms.

    Query text is never passed to MATCH directly: it would be parsed as FTS5
    syntax, so a stray quote or a word like NOT would change the query or make
    it fail. Matching any term rather than all of them also keeps ranking
    behaviour aligned with InMemoryBM25Index.
    """
    terms = _QUERY_TERMS.findall(query)
    if not terms:
        return None
    return " OR ".join(f'"{term}"' for term in terms)


def _synchronization_triggers() -> str:
    """Keep the FTS5 shadow tables in step with the content table.

    An external-content FTS5 table stores no copy of the text, so every
    write to the content table has to be mirrored into the index. Doing it
    with triggers means the upsert in index() and the plain DELETE in
    delete() need no FTS5-specific code.
    """
    return f"""
        CREATE TRIGGER IF NOT EXISTS {_DOCUMENTS}_after_insert AFTER INSERT ON {_DOCUMENTS} BEGIN
            INSERT INTO {_SEARCH}(rowid, text) VALUES (new.rowid, new.text);
        END;

        CREATE TRIGGER IF NOT EXISTS {_DOCUMENTS}_after_delete AFTER DELETE ON {_DOCUMENTS} BEGIN
            INSERT INTO {_SEARCH}({_SEARCH}, rowid, text) VALUES ('delete', old.rowid, old.text);
        END;

        CREATE TRIGGER IF NOT EXISTS {_DOCUMENTS}_after_update AFTER UPDATE ON {_DOCUMENTS} BEGIN
            INSERT INTO {_SEARCH}({_SEARCH}, rowid, text) VALUES ('delete', old.rowid, old.text);
            INSERT INTO {_SEARCH}(rowid, text) VALUES (new.rowid, new.text);
        END;
    """
