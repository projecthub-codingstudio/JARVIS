"""HybridSearch — fuses FTS and vector results using Reciprocal Rank Fusion.

Implements HybridFusionProtocol to combine BM25 (FTS) and dense vector
search results into a single ranked list.
"""

from __future__ import annotations

from typing import Sequence

from jarvis.contracts import (
    HybridFusionProtocol,
    HybridSearchResult,
    SearchHit,
    VectorHit,
)


class HybridSearch:
    """Reciprocal Rank Fusion over FTS + vector results.

    Implements HybridFusionProtocol.
    Phase 0 stub: returns a single fused result from the first hits.
    """

    def __init__(self, *, rrf_k: int = 60) -> None:
        """Initialize with RRF constant.

        Args:
            rrf_k: The k constant for RRF scoring (default 60).
        """
        self._rrf_k = rrf_k

    def fuse(
        self,
        fts_hits: Sequence[SearchHit],
        vector_hits: Sequence[VectorHit],
        top_k: int = 10,
    ) -> list[HybridSearchResult]:
        """Fuse FTS and vector results with Reciprocal Rank Fusion.

        Args:
            fts_hits: Results from FTS retrieval.
            vector_hits: Results from vector retrieval.
            top_k: Maximum number of fused results to return.

        Returns:
            Ranked list of HybridSearchResult.
        """
        # Pre-build vector rank lookup for O(1) access (was O(n) linear scan)
        vector_rank_map: dict[str, int] = {
            vh.chunk_id: vr for vr, vh in enumerate(vector_hits, 1)
        }

        chunk_ids: set[str] = set()
        results: list[HybridSearchResult] = []

        for rank, hit in enumerate(fts_hits, 1):
            if hit.chunk_id not in chunk_ids:
                chunk_ids.add(hit.chunk_id)
                vector_rank = vector_rank_map.get(hit.chunk_id)
                rrf_score = 1.0 / (self._rrf_k + rank)
                if vector_rank is not None:
                    rrf_score += 1.0 / (self._rrf_k + vector_rank)
                results.append(
                    HybridSearchResult(
                        chunk_id=hit.chunk_id,
                        document_id=hit.document_id,
                        rrf_score=rrf_score,
                        fts_rank=rank,
                        vector_rank=vector_rank,
                        snippet=hit.snippet,
                    )
                )

        for rank, hit in enumerate(vector_hits, 1):
            if hit.chunk_id not in chunk_ids:
                chunk_ids.add(hit.chunk_id)
                rrf_score = 1.0 / (self._rrf_k + rank)
                results.append(
                    HybridSearchResult(
                        chunk_id=hit.chunk_id,
                        document_id=hit.document_id,
                        rrf_score=rrf_score,
                        vector_rank=rank,
                        snippet="",
                    )
                )

        results.sort(key=lambda r: r.rrf_score, reverse=True)
        return results[:top_k]
