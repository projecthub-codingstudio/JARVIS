"""Tests for parallel FTS + Vector search and RRF dict optimization."""
from __future__ import annotations

import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Sequence

import pytest

from jarvis.app.bootstrap import init_database
from jarvis.app.config import JarvisConfig
from jarvis.contracts import SearchHit, TypedQueryFragment, VectorHit
from jarvis.indexing.chunker import Chunker
from jarvis.indexing.index_pipeline import IndexPipeline
from jarvis.indexing.parsers import DocumentParser
from jarvis.indexing.tombstone import TombstoneManager
from jarvis.retrieval.fts_index import FTSIndex
from jarvis.retrieval.hybrid_search import HybridSearch
from jarvis.retrieval.vector_index import VectorIndex


class FakeEmbeddingRuntime:
    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        return [[0.0] * 8 for _ in texts]


@pytest.fixture
def indexed_db(tmp_path: Path) -> sqlite3.Connection:
    config = JarvisConfig(watched_folders=[tmp_path], data_dir=tmp_path / ".jarvis")
    db = init_database(config)
    pipeline = IndexPipeline(
        db=db,
        parser=DocumentParser(),
        chunker=Chunker(max_chunk_bytes=512, overlap_bytes=64),
        tombstone_manager=TombstoneManager(db=db),
        embedding_runtime=FakeEmbeddingRuntime(),
    )
    (tmp_path / "doc1.md").write_text("# Architecture\n\nMonolith-first design pattern.")
    (tmp_path / "doc2.md").write_text("# 음성 인식\n\nWhisper.cpp 기반 시스템.")
    pipeline.index_file(tmp_path / "doc1.md")
    pipeline.index_file(tmp_path / "doc2.md")
    return db


class TestParallelFTSSearch:
    """Verify FTS search works correctly from multiple threads with WAL mode."""

    def test_concurrent_fts_reads(self, indexed_db: sqlite3.Connection) -> None:
        """Two FTS searches running in parallel should both return valid results."""
        fts = FTSIndex(db=indexed_db)
        frags_en = [TypedQueryFragment(text="architecture", language="en", query_type="keyword")]
        frags_ko = [TypedQueryFragment(text="음성 인식", language="ko", query_type="keyword")]

        with ThreadPoolExecutor(max_workers=2) as executor:
            future_en = executor.submit(fts.search, frags_en, 10)
            future_ko = executor.submit(fts.search, frags_ko, 10)
            hits_en = future_en.result()
            hits_ko = future_ko.result()

        assert len(hits_en) >= 1
        assert len(hits_ko) >= 1

    def test_parallel_fts_and_vector_stub(self, indexed_db: sqlite3.Connection) -> None:
        """FTS + stub Vector in parallel should not raise."""
        fts = FTSIndex(db=indexed_db)
        vector = VectorIndex()
        fragments = [TypedQueryFragment(text="architecture", language="en", query_type="keyword")]

        with ThreadPoolExecutor(max_workers=2) as executor:
            fts_future = executor.submit(fts.search, fragments, 10)
            vec_future = executor.submit(vector.search, fragments, 10)
            fts_hits = fts_future.result()
            vec_hits = vec_future.result()

        assert len(fts_hits) >= 1
        assert isinstance(vec_hits, list)


class TestRRFFusionDictOptimization:
    """Verify RRF fusion produces identical results after dict optimization."""

    def _make_fts_hits(self) -> list[SearchHit]:
        return [
            SearchHit(chunk_id="c1", document_id="d1", score=10.0, snippet="chunk 1"),
            SearchHit(chunk_id="c2", document_id="d1", score=8.0, snippet="chunk 2"),
            SearchHit(chunk_id="c3", document_id="d2", score=6.0, snippet="chunk 3"),
        ]

    def _make_vector_hits(self) -> list[VectorHit]:
        return [
            VectorHit(chunk_id="c2", document_id="d1", score=0.9, embedding_distance=0.1),
            VectorHit(chunk_id="c4", document_id="d3", score=0.8, embedding_distance=0.2),
            VectorHit(chunk_id="c1", document_id="d1", score=0.7, embedding_distance=0.3),
        ]

    def test_fuse_correct_scores(self) -> None:
        fusion = HybridSearch(rrf_k=60)
        results = fusion.fuse(self._make_fts_hits(), self._make_vector_hits(), top_k=10)

        scores = {r.chunk_id: r.rrf_score for r in results}

        # c1: FTS rank 1 + Vector rank 3 → 1/61 + 1/63
        assert abs(scores["c1"] - (1 / 61 + 1 / 63)) < 1e-9
        # c2: FTS rank 2 + Vector rank 1 → 1/62 + 1/61
        assert abs(scores["c2"] - (1 / 62 + 1 / 61)) < 1e-9
        # c3: FTS rank 3 only → 1/63
        assert abs(scores["c3"] - 1 / 63) < 1e-9
        # c4: Vector rank 2 only → 1/62
        assert abs(scores["c4"] - 1 / 62) < 1e-9

    def test_fuse_ranking_order(self) -> None:
        fusion = HybridSearch(rrf_k=60)
        results = fusion.fuse(self._make_fts_hits(), self._make_vector_hits(), top_k=10)

        # c2 should rank highest (appears in both, vector rank 1)
        assert results[0].chunk_id == "c2"
        # Scores should be strictly descending
        for i in range(len(results) - 1):
            assert results[i].rrf_score >= results[i + 1].rrf_score

    def test_fuse_preserves_ranks(self) -> None:
        fusion = HybridSearch(rrf_k=60)
        results = fusion.fuse(self._make_fts_hits(), self._make_vector_hits(), top_k=10)

        rank_map = {r.chunk_id: r for r in results}
        assert rank_map["c1"].fts_rank == 1
        assert rank_map["c1"].vector_rank == 3
        assert rank_map["c2"].fts_rank == 2
        assert rank_map["c2"].vector_rank == 1
        assert rank_map["c3"].fts_rank == 3
        assert rank_map["c3"].vector_rank is None
        assert rank_map["c4"].fts_rank is None
        assert rank_map["c4"].vector_rank == 2

    def test_fuse_top_k_limit(self) -> None:
        fusion = HybridSearch(rrf_k=60)
        results = fusion.fuse(self._make_fts_hits(), self._make_vector_hits(), top_k=2)
        assert len(results) == 2

    def test_fuse_empty_inputs(self) -> None:
        fusion = HybridSearch(rrf_k=60)
        assert fusion.fuse([], [], top_k=10) == []
        assert len(fusion.fuse(self._make_fts_hits(), [], top_k=10)) == 3
        assert len(fusion.fuse([], self._make_vector_hits(), top_k=10)) == 3


class TestCheckSameThreadDisabled:
    """Verify init_database creates connections with check_same_thread=False."""

    def test_connection_usable_from_other_thread(self, tmp_path: Path) -> None:
        config = JarvisConfig(watched_folders=[tmp_path], data_dir=tmp_path / ".jarvis")
        db = init_database(config)

        def query_from_thread() -> str:
            return db.execute("PRAGMA journal_mode").fetchone()[0]

        with ThreadPoolExecutor(max_workers=1) as executor:
            result = executor.submit(query_from_thread).result()

        assert result == "wal"
        db.close()
