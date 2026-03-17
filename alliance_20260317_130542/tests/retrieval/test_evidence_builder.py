"""Tests for EvidenceBuilder."""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Sequence

import pytest

from jarvis.app.bootstrap import init_database
from jarvis.app.config import JarvisConfig
from jarvis.contracts import (
    CitationState,
    EvidenceBuilderProtocol,
    HybridSearchResult,
    TypedQueryFragment,
)
from jarvis.indexing.chunker import Chunker
from jarvis.indexing.index_pipeline import IndexPipeline
from jarvis.indexing.parsers import DocumentParser
from jarvis.indexing.tombstone import TombstoneManager
from jarvis.retrieval.evidence_builder import EvidenceBuilder


class FakeEmbeddingRuntime:
    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        return [[0.0] * 8 for _ in texts]


@pytest.fixture
def indexed_setup(tmp_path: Path) -> tuple[sqlite3.Connection, str, str]:
    config = JarvisConfig(watched_folders=[tmp_path], data_dir=tmp_path / ".jarvis")
    db = init_database(config)
    pipeline = IndexPipeline(
        db=db, parser=DocumentParser(),
        chunker=Chunker(max_chunk_bytes=512, overlap_bytes=64),
        tombstone_manager=TombstoneManager(db=db),
        embedding_runtime=FakeEmbeddingRuntime(),
    )
    (tmp_path / "doc.md").write_text("Architecture design for JARVIS project.")
    record = pipeline.index_file(tmp_path / "doc.md")
    chunk_row = db.execute(
        "SELECT chunk_id FROM chunks WHERE document_id = ?",
        (record.document_id,),
    ).fetchone()
    return db, record.document_id, chunk_row[0]


class TestEvidenceBuilderNoDb:
    def test_stub_builds_evidence(self) -> None:
        builder = EvidenceBuilder()
        results = [HybridSearchResult(chunk_id="c1", document_id="d1", rrf_score=0.5, snippet="text")]
        fragments = [TypedQueryFragment(text="q", language="ko", query_type="keyword")]
        evidence = builder.build(results, fragments)
        assert not evidence.is_empty
        assert evidence.items[0].citation.label == "[1]"

    def test_empty_results(self) -> None:
        builder = EvidenceBuilder()
        evidence = builder.build([], [TypedQueryFragment(text="q", language="ko", query_type="keyword")])
        assert evidence.is_empty

    def test_protocol_conformance(self) -> None:
        assert isinstance(EvidenceBuilder(), EvidenceBuilderProtocol)


class TestEvidenceBuilderWithDb:
    def test_resolves_chunk_text(self, indexed_setup: tuple[sqlite3.Connection, str, str]) -> None:
        db, doc_id, chunk_id = indexed_setup
        builder = EvidenceBuilder(db=db)
        results = [HybridSearchResult(chunk_id=chunk_id, document_id=doc_id, rrf_score=0.5, snippet="")]
        fragments = [TypedQueryFragment(text="arch", language="en", query_type="keyword")]
        evidence = builder.build(results, fragments)
        assert not evidence.is_empty
        assert "Architecture" in evidence.items[0].text or "design" in evidence.items[0].text

    def test_sets_source_path(self, indexed_setup: tuple[sqlite3.Connection, str, str]) -> None:
        db, doc_id, chunk_id = indexed_setup
        builder = EvidenceBuilder(db=db)
        results = [HybridSearchResult(chunk_id=chunk_id, document_id=doc_id, rrf_score=0.5)]
        fragments = [TypedQueryFragment(text="q", language="en", query_type="keyword")]
        evidence = builder.build(results, fragments)
        assert evidence.items[0].source_path

    def test_freshness_check_valid(self, indexed_setup: tuple[sqlite3.Connection, str, str]) -> None:
        db, doc_id, chunk_id = indexed_setup
        builder = EvidenceBuilder(db=db)
        results = [HybridSearchResult(chunk_id=chunk_id, document_id=doc_id, rrf_score=0.5)]
        fragments = [TypedQueryFragment(text="q", language="en", query_type="keyword")]
        evidence = builder.build(results, fragments)
        assert evidence.items[0].citation.state == CitationState.VALID

    def test_rejects_unresolvable_chunk(self, indexed_setup: tuple[sqlite3.Connection, str, str]) -> None:
        db, doc_id, _ = indexed_setup
        builder = EvidenceBuilder(db=db)
        results = [HybridSearchResult(chunk_id="nonexistent", document_id=doc_id, rrf_score=0.5)]
        fragments = [TypedQueryFragment(text="q", language="en", query_type="keyword")]
        evidence = builder.build(results, fragments)
        assert evidence.is_empty
