"""FTSIndex — full-text search retrieval via SQLite FTS5."""
from __future__ import annotations

import sqlite3
from typing import Sequence

from jarvis.contracts import SearchHit, TypedQueryFragment


class FTSIndex:
    """Full-text search index backed by SQLite FTS5."""

    def __init__(self, *, db: sqlite3.Connection | None = None) -> None:
        self._db = db

    def search(
        self, fragments: Sequence[TypedQueryFragment], top_k: int = 10
    ) -> list[SearchHit]:
        if self._db is None:
            return self._stub_search()

        terms: list[str] = []
        for frag in fragments:
            if frag.query_type == "keyword":
                words = frag.text.split()
                terms.extend(w for w in words if w.strip())

        if not terms:
            return []

        fts_query = " OR ".join(f'"{t}"' for t in terms)

        try:
            rows = self._db.execute(
                "SELECT c.chunk_id, c.document_id, c.text, c.byte_start, c.byte_end,"
                " c.line_start, c.line_end, rank"
                " FROM chunks c"
                " JOIN chunks_fts f ON c.rowid = f.rowid"
                " WHERE chunks_fts MATCH ?"
                " ORDER BY rank"
                " LIMIT ?",
                (fts_query, top_k),
            ).fetchall()
        except sqlite3.OperationalError:
            return []

        hits: list[SearchHit] = []
        for row in rows:
            hits.append(SearchHit(
                chunk_id=row[0],
                document_id=row[1],
                score=abs(row[7]) if row[7] else 0.0,
                snippet=row[2][:200] if row[2] else "",
                byte_range=(row[3], row[4]),
                line_range=(row[5], row[6]),
            ))
        return hits

    def _stub_search(self) -> list[SearchHit]:
        return [
            SearchHit(
                chunk_id="stub-chunk-1",
                document_id="stub-doc-1",
                score=0.95,
                snippet="stub FTS result",
            ),
        ]
