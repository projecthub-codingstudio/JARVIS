"""FTSIndex — full-text search retrieval via SQLite FTS5.

Per Spec Task 0.4: FTS5 search must use morpheme expansion via kiwipiepy
for Korean queries. Mixed Korean/English is handled by combining
morpheme-expanded Korean tokens with raw English tokens.
"""
from __future__ import annotations

import logging
import sqlite3
import time
from typing import Sequence

from jarvis.contracts import SearchHit, TypedQueryFragment
from jarvis.observability.metrics import MetricName, MetricsCollector
from jarvis.retrieval.tokenizer_kiwi import KiwiTokenizer

logger = logging.getLogger(__name__)

# Singleton tokenizer (Kiwi model loading is expensive)
_kiwi: KiwiTokenizer | None = None


def _get_kiwi() -> KiwiTokenizer:
    global _kiwi
    if _kiwi is None:
        _kiwi = KiwiTokenizer()
    return _kiwi


class FTSIndex:
    """Full-text search index backed by SQLite FTS5.

    Uses Kiwi morpheme expansion for Korean query terms
    per Spec Task 0.4.
    """

    def __init__(
        self,
        *,
        db: sqlite3.Connection | None = None,
        metrics: MetricsCollector | None = None,
    ) -> None:
        self._db = db
        self._metrics = metrics

    def search(
        self, fragments: Sequence[TypedQueryFragment], top_k: int = 20
    ) -> list[SearchHit]:
        if self._db is None:
            return self._stub_search()

        terms: list[str] = []
        kiwi = _get_kiwi()

        for frag in fragments:
            if frag.query_type == "keyword":
                if frag.language == "ko":
                    # Korean: content-word morphemes via Kiwi (nouns, verbs only)
                    content_words = kiwi.tokenize_nouns(frag.text)
                    terms.extend(m for m in content_words if len(m) > 0)
                    # Also add original whitespace-split terms for compound matching
                    terms.extend(w for w in frag.text.split() if w.strip() and len(w) > 1)
                else:
                    # English/code: whitespace split
                    terms.extend(w for w in frag.text.split() if w.strip())

        if not terms:
            return []

        # Deduplicate while preserving order
        seen: set[str] = set()
        unique_terms: list[str] = []
        for t in terms:
            if t not in seen:
                seen.add(t)
                unique_terms.append(t)

        # Search both text and lexical_morphs columns
        # FTS5 syntax: {col1 col2 : term} searches both columns
        fts_query = " OR ".join(
            f'{{text lexical_morphs}} : "{t}"' for t in unique_terms
        )
        logger.debug("FTS query: %s", fts_query)

        started_at = time.perf_counter()
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
        except sqlite3.OperationalError as exc:
            if self._metrics is not None and "locked" in str(exc).lower():
                self._metrics.increment(MetricName.SQLITE_LOCK_COUNT)
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

        if self._metrics is not None:
            elapsed_ms = (time.perf_counter() - started_at) * 1000
            self._metrics.record(
                MetricName.QUERY_LATENCY_MS,
                elapsed_ms,
                tags={"stage": "fts_search", "result_count": str(len(hits))},
            )
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
