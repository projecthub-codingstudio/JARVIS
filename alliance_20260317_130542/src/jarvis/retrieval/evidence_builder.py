"""EvidenceBuilder — builds verified evidence sets from ranked search results.

When db is provided, resolves chunk text and verifies citation freshness.
Without db, falls back to stub behavior for backward compatibility.

Per Spec Section 11.2:
  - Applies freshness score boost for recently modified files
  - STALE auto-detection via content hash comparison
  - STALE/MISSING citations are included but flagged for warning display
"""
from __future__ import annotations

import sqlite3
from typing import Sequence

from jarvis.contracts import (
    CitationRecord,
    CitationState,
    DocumentRecord,
    EvidenceItem,
    HybridSearchResult,
    IndexingStatus,
    TypedQueryFragment,
    VerifiedEvidenceSet,
)
from jarvis.retrieval.freshness import FreshnessChecker


class EvidenceBuilder:
    """Builds VerifiedEvidenceSet from hybrid search results."""

    def __init__(self, *, db: sqlite3.Connection | None = None) -> None:
        self._db = db
        self._freshness = FreshnessChecker()

    def build(
        self,
        results: Sequence[HybridSearchResult],
        fragments: Sequence[TypedQueryFragment],
    ) -> VerifiedEvidenceSet:
        if not results:
            return VerifiedEvidenceSet(items=(), query_fragments=tuple(fragments))

        if self._db is None:
            return self._stub_build(results, fragments)

        items: list[EvidenceItem] = []
        for i, result in enumerate(results, 1):
            chunk_row = self._db.execute(
                "SELECT text, heading_path FROM chunks WHERE chunk_id = ?",
                (result.chunk_id,),
            ).fetchone()
            if chunk_row is None:
                continue

            doc_row = self._db.execute(
                "SELECT document_id, path, content_hash, size_bytes, indexing_status"
                " FROM documents WHERE document_id = ?",
                (result.document_id,),
            ).fetchone()
            if doc_row is None:
                continue

            doc = DocumentRecord(
                document_id=doc_row[0],
                path=doc_row[1],
                content_hash=doc_row[2],
                size_bytes=doc_row[3],
                indexing_status=IndexingStatus(doc_row[4]),
            )

            citation = CitationRecord(
                document_id=result.document_id,
                chunk_id=result.chunk_id,
                label=f"[{i}]",
                state=CitationState.VALID,
            )
            citation = self._freshness.refresh_citation(citation, doc)

            # Freshness score boost: recently modified files rank higher
            freshness_boost = self._freshness.compute_freshness_boost(doc)
            boosted_score = result.rrf_score + freshness_boost

            text = chunk_row[0] if chunk_row[0] else result.snippet
            heading_path = chunk_row[1] if len(chunk_row) > 1 and chunk_row[1] else ""
            items.append(EvidenceItem(
                chunk_id=result.chunk_id,
                document_id=result.document_id,
                text=text,
                citation=citation,
                relevance_score=boosted_score,
                source_path=doc.path,
                heading_path=heading_path,
            ))

        return VerifiedEvidenceSet(
            items=tuple(items), query_fragments=tuple(fragments)
        )

    def _stub_build(
        self,
        results: Sequence[HybridSearchResult],
        fragments: Sequence[TypedQueryFragment],
    ) -> VerifiedEvidenceSet:
        items: list[EvidenceItem] = []
        for i, result in enumerate(results, 1):
            citation = CitationRecord(
                document_id=result.document_id,
                chunk_id=result.chunk_id,
                label=f"[{i}]",
                state=CitationState.VALID,
            )
            items.append(EvidenceItem(
                chunk_id=result.chunk_id,
                document_id=result.document_id,
                text=result.snippet or f"Evidence from {result.document_id}",
                citation=citation,
                relevance_score=result.rrf_score,
            ))
        return VerifiedEvidenceSet(
            items=tuple(items), query_fragments=tuple(fragments)
        )
