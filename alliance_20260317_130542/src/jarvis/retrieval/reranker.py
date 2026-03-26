"""Reranker — cross-encoder reranking for hybrid search results.

Uses a lightweight cross-encoder model to re-score candidate chunks
against the original query. This filters out FTS noise and promotes
semantically relevant results.

Per design: placed between RRF fusion and evidence building.
"""
from __future__ import annotations

import logging
import os
import time
from typing import Sequence

from jarvis.contracts import HybridSearchResult, TypedQueryFragment
from jarvis.observability.metrics import MetricName, MetricsCollector

logger = logging.getLogger(__name__)

# Multilingual cross-encoder for Korean + English queries (~450MB)
_DEFAULT_MODEL = "cross-encoder/mmarco-mMiniLMv2-L12-H384-v1"
_RERANK_BATCH_SIZE = 16


class Reranker:
    """Cross-encoder reranker for hybrid search results.

    Lazily loads the cross-encoder model on first use.
    Falls back to pass-through (no reranking) if unavailable.
    """

    def __init__(
        self,
        *,
        model_id: str = _DEFAULT_MODEL,
        metrics: MetricsCollector | None = None,
    ) -> None:
        self._model_id = model_id
        self._metrics = metrics
        self._model: object | None = None
        self._available: bool | None = None

    def _check_available(self) -> bool:
        if self._available is not None:
            return self._available
        try:
            from sentence_transformers import CrossEncoder  # noqa: F401
            self._available = True
        except ImportError:
            logger.warning("CrossEncoder not available — reranking disabled")
            self._available = False
        return self._available

    def _ensure_model(self) -> object | None:
        if self._model is not None:
            return self._model
        if not self._check_available():
            return None
        try:
            os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")
            logging.getLogger("sentence_transformers").setLevel(logging.ERROR)
            logging.getLogger("transformers").setLevel(logging.ERROR)

            from sentence_transformers import CrossEncoder
            # Force CPU to avoid Metal GPU conflicts with MLX LLM
            self._model = CrossEncoder(self._model_id, device="cpu")
            logger.info("Loaded reranker model: %s (cpu)", self._model_id)
            return self._model
        except Exception as e:
            logger.warning("Failed to load reranker: %s", e)
            self._available = False
            return None

    def rerank(
        self,
        query: str,
        results: Sequence[HybridSearchResult],
        *,
        top_k: int = 10,
        chunk_texts: dict[str, str] | None = None,
    ) -> list[HybridSearchResult]:
        """Rerank hybrid search results using cross-encoder scoring.

        Args:
            query: Original user query text.
            results: RRF-fused candidates to rerank.
            top_k: Maximum results to return after reranking.
            chunk_texts: Mapping of chunk_id → full chunk text.
                         If not provided, uses snippet field.

        Returns:
            Reranked list of HybridSearchResult with updated rrf_score.
        """
        if not results:
            return []

        model = self._ensure_model()
        if model is None:
            # Fallback: return results unchanged
            return list(results[:top_k])

        started_at = time.perf_counter()

        # Build (query, passage) pairs for cross-encoder.
        # Do not apply naive character-based truncation here.
        # CrossEncoder already tokenizes with its own max_length, and a
        # 512-character cutoff is especially harmful for Korean passages.
        pairs: list[tuple[str, str]] = []
        for r in results:
            text = ""
            if chunk_texts and r.chunk_id in chunk_texts:
                text = chunk_texts[r.chunk_id]
            elif r.snippet:
                text = r.snippet
            pairs.append((query, text))

        # Score with cross-encoder
        try:
            scores = model.predict(pairs, batch_size=_RERANK_BATCH_SIZE)
        except Exception as e:
            logger.warning("Reranking failed: %s — returning original order", e)
            return list(results[:top_k])

        # Combine cross-encoder score with original RRF score
        import math
        reranked: list[tuple[float, HybridSearchResult]] = []
        for result, ce_score in zip(results, scores):
            ce_norm = float(ce_score)
            if math.isnan(ce_norm) or math.isinf(ce_norm):
                ce_norm = 0.0
            # Combined score: weight cross-encoder heavily (0.7) + RRF (0.3)
            combined = 0.7 * ce_norm + 0.3 * (result.rrf_score * 60)  # Scale RRF
            reranked.append((combined, result))

        reranked.sort(key=lambda x: x[0], reverse=True)

        elapsed_ms = (time.perf_counter() - started_at) * 1000
        logger.info("Reranked %d results in %.0fms", len(results), elapsed_ms)

        if self._metrics is not None:
            self._metrics.record(
                MetricName.QUERY_LATENCY_MS, elapsed_ms,
                tags={"stage": "rerank"},
            )

        # Return with updated scores
        final: list[HybridSearchResult] = []
        for combined_score, r in reranked[:top_k]:
            final.append(HybridSearchResult(
                chunk_id=r.chunk_id,
                document_id=r.document_id,
                rrf_score=combined_score,
                fts_rank=r.fts_rank,
                vector_rank=r.vector_rank,
                snippet=r.snippet,
            ))
        return final

    def unload(self) -> None:
        """Unload the cross-encoder model."""
        if self._model is not None:
            del self._model
            self._model = None
            logger.info("Unloaded reranker model")
