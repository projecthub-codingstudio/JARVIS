"""Benchmark harnesses for retrieval quality and latency."""

from __future__ import annotations

import json
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from statistics import mean
from typing import Any

from jarvis.app.bootstrap import init_database
from jarvis.app.config import JarvisConfig
from jarvis.indexing.chunker import Chunker
from jarvis.indexing.index_pipeline import IndexPipeline
from jarvis.indexing.parsers import DocumentParser
from jarvis.indexing.tombstone import TombstoneManager
from jarvis.observability.metrics import MetricsCollector
from jarvis.retrieval.evidence_builder import EvidenceBuilder
from jarvis.retrieval.fts_index import FTSIndex
from jarvis.retrieval.hybrid_search import HybridSearch
from jarvis.retrieval.query_decomposer import QueryDecomposer
from jarvis.retrieval.vector_index import VectorIndex


@dataclass(frozen=True)
class BenchmarkQueryResult:
    """Per-query benchmark outcome."""

    query_id: str
    category: str
    latency_ms: float
    expected_doc_ids: tuple[str, ...]
    actual_doc_ids: tuple[str, ...]
    top5_hit: bool
    evidence_count: int


@dataclass(frozen=True)
class PerfReport:
    """Aggregate benchmark report."""

    query_count: int
    avg_latency_ms: float
    p95_latency_ms: float
    top5_accuracy: float
    category_accuracy: dict[str, float]
    results: tuple[BenchmarkQueryResult, ...]


def _percentile(values: list[float], q: float) -> float:
    """Return a simple percentile estimate from sorted values."""
    if not values:
        return 0.0
    sorted_values = sorted(values)
    index = max(0, min(len(sorted_values) - 1, int(round((len(sorted_values) - 1) * q))))
    return sorted_values[index]


def _load_queries(queries_path: Path) -> list[dict[str, Any]]:
    payload = json.loads(queries_path.read_text(encoding="utf-8"))
    queries = payload.get("queries")
    if not isinstance(queries, list):
        raise ValueError(f"Invalid benchmark file: {queries_path}")
    return queries


def _index_corpus(corpus_dir: Path, metrics: MetricsCollector) -> tuple[object, Path]:
    temp_dir = Path(tempfile.mkdtemp(prefix="jarvis-bench-"))
    config = JarvisConfig(watched_folders=[corpus_dir], data_dir=temp_dir / ".jarvis")
    db = init_database(config)
    pipeline = IndexPipeline(
        db=db,  # type: ignore[arg-type]
        parser=DocumentParser(),
        chunker=Chunker(max_chunk_bytes=512, overlap_bytes=64),
        tombstone_manager=TombstoneManager(db=db),  # type: ignore[arg-type]
        embedding_runtime=VectorlessEmbeddingRuntime(),
        metrics=metrics,
    )

    for path in sorted(corpus_dir.iterdir()):
        if path.is_file():
            pipeline.index_file(path)

    return db, temp_dir


class VectorlessEmbeddingRuntime:
    """Benchmark-safe embedding stub for FTS-first evaluation."""

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [[0.0] * 8 for _ in texts]


def run_query_latency_bench(corpus_dir: Path, queries_path: Path) -> PerfReport:
    """Run the 50-query retrieval benchmark over a corpus fixture."""
    metrics = MetricsCollector()
    db, temp_dir = _index_corpus(corpus_dir, metrics)
    try:
        decomposer = QueryDecomposer()
        fts = FTSIndex(db=db, metrics=metrics)  # type: ignore[arg-type]
        vector = VectorIndex(metrics=metrics)
        fusion = HybridSearch()
        evidence_builder = EvidenceBuilder(db=db, metrics=metrics)  # type: ignore[arg-type]

        results: list[BenchmarkQueryResult] = []
        for query in _load_queries(queries_path):
            started_at = time.perf_counter()
            fragments = decomposer.decompose(str(query["text"]))
            with ThreadPoolExecutor(max_workers=2) as executor:
                fts_future = executor.submit(fts.search, fragments, 10)
                vector_future = executor.submit(vector.search, fragments, 10)
                fts_hits = fts_future.result()
                vector_hits = vector_future.result()
            hybrid_results = fusion.fuse(fts_hits, vector_hits, top_k=10)
            evidence = evidence_builder.build(hybrid_results, fragments)
            latency_ms = (time.perf_counter() - started_at) * 1000

            actual_doc_ids = tuple(
                Path(item.source_path).stem
                for item in evidence.items[:5]
                if item.source_path
            )
            expected_doc_ids = tuple(str(doc_id) for doc_id in query.get("expected_doc_ids", []))
            top5_hit = any(doc_id in expected_doc_ids for doc_id in actual_doc_ids)

            results.append(BenchmarkQueryResult(
                query_id=str(query["id"]),
                category=str(query.get("category", "unknown")),
                latency_ms=latency_ms,
                expected_doc_ids=expected_doc_ids,
                actual_doc_ids=actual_doc_ids,
                top5_hit=top5_hit,
                evidence_count=len(evidence.items),
            ))

        latencies = [result.latency_ms for result in results]
        category_accuracy: dict[str, float] = {}
        for category in sorted({result.category for result in results}):
            category_results = [result for result in results if result.category == category]
            hits = sum(1 for result in category_results if result.top5_hit)
            category_accuracy[category] = hits / len(category_results) if category_results else 0.0

        hits = sum(1 for result in results if result.top5_hit)
        return PerfReport(
            query_count=len(results),
            avg_latency_ms=mean(latencies) if latencies else 0.0,
            p95_latency_ms=_percentile(latencies, 0.95),
            top5_accuracy=(hits / len(results)) if results else 0.0,
            category_accuracy=category_accuracy,
            results=tuple(results),
        )
    finally:
        try:
            db.close()  # type: ignore[union-attr]
        finally:
            for path in sorted(temp_dir.rglob("*"), reverse=True):
                if path.is_file():
                    path.unlink(missing_ok=True)
                elif path.is_dir():
                    path.rmdir()
            temp_dir.rmdir()
