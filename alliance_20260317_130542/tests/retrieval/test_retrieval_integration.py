"""Integration test: full retrieval pipeline from indexed docs to evidence."""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Sequence

import pytest

from jarvis.app.bootstrap import init_database
from jarvis.app.config import JarvisConfig
from jarvis.contracts import CitationState, TypedQueryFragment
from jarvis.indexing.chunker import Chunker
from jarvis.indexing.index_pipeline import IndexPipeline
from jarvis.indexing.parsers import DocumentParser
from jarvis.indexing.tombstone import TombstoneManager
from jarvis.retrieval.evidence_builder import EvidenceBuilder
from jarvis.retrieval.fts_index import FTSIndex
from jarvis.retrieval.hybrid_search import HybridSearch
from jarvis.retrieval.query_decomposer import QueryDecomposer
from jarvis.retrieval.vector_index import VectorIndex


class FakeEmbeddingRuntime:
    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        return [[0.0] * 8 for _ in texts]


@pytest.fixture
def full_setup(tmp_path: Path) -> tuple[sqlite3.Connection, Path]:
    config = JarvisConfig(watched_folders=[tmp_path], data_dir=tmp_path / ".jarvis")
    db = init_database(config)
    pipeline = IndexPipeline(
        db=db,
        parser=DocumentParser(),
        chunker=Chunker(max_chunk_bytes=512, overlap_bytes=64),
        tombstone_manager=TombstoneManager(db=db),
        embedding_runtime=FakeEmbeddingRuntime(),
    )
    (tmp_path / "architecture.md").write_text(
        "# JARVIS Architecture\n\nThe system uses a monolith-first design.\n"
        "Protocol interfaces define all module boundaries."
    )
    (tmp_path / "korean_doc.md").write_text(
        "# 음성 인식 시스템\n\n로컬 환경에서 동작하는 음성 인식 엔진을 설계합니다.\n"
        "Whisper.cpp를 사용하여 한국어 음성을 텍스트로 변환합니다."
    )
    (tmp_path / "retrieval.py").write_text(
        '"""Retrieval pipeline for JARVIS."""\n\n'
        'def search(query: str) -> list:\n    """Search indexed documents."""\n    pass\n'
    )
    for f in tmp_path.glob("*"):
        if f.is_file():
            pipeline.index_file(f)
    return db, tmp_path


@pytest.mark.integration
class TestRetrievalRoundTrip:
    def test_english_query_finds_architecture(
        self, full_setup: tuple[sqlite3.Connection, Path]
    ) -> None:
        db, _ = full_setup
        decomposer = QueryDecomposer()
        fts = FTSIndex(db=db)
        vector = VectorIndex()
        fusion = HybridSearch()
        evidence_builder = EvidenceBuilder(db=db)

        fragments = decomposer.decompose("architecture design")
        fts_hits = fts.search(fragments)
        vector_hits = vector.search(fragments)
        hybrid = fusion.fuse(fts_hits, vector_hits)
        evidence = evidence_builder.build(hybrid, fragments)

        assert not evidence.is_empty
        texts_joined = " ".join(item.text.lower() for item in evidence.items)
        assert "monolith" in texts_joined or "architecture" in texts_joined
        assert all(item.citation.state == CitationState.VALID for item in evidence.items)

    def test_korean_query_finds_korean_doc(
        self, full_setup: tuple[sqlite3.Connection, Path]
    ) -> None:
        db, _ = full_setup
        decomposer = QueryDecomposer()
        fts = FTSIndex(db=db)
        vector = VectorIndex()
        fusion = HybridSearch()
        evidence_builder = EvidenceBuilder(db=db)

        fragments = decomposer.decompose("음성 인식 시스템")
        fts_hits = fts.search(fragments)
        vector_hits = vector.search(fragments)
        hybrid = fusion.fuse(fts_hits, vector_hits)
        evidence = evidence_builder.build(hybrid, fragments)

        assert not evidence.is_empty
        assert any("음성" in item.text for item in evidence.items)

    def test_code_query_finds_python(
        self, full_setup: tuple[sqlite3.Connection, Path]
    ) -> None:
        db, _ = full_setup
        decomposer = QueryDecomposer()
        fts = FTSIndex(db=db)
        fusion = HybridSearch()
        evidence_builder = EvidenceBuilder(db=db)

        fragments = decomposer.decompose("search function")
        fts_hits = fts.search(fragments)
        hybrid = fusion.fuse(fts_hits, [])
        evidence = evidence_builder.build(hybrid, fragments)

        assert not evidence.is_empty

    def test_no_match_returns_empty_evidence(
        self, full_setup: tuple[sqlite3.Connection, Path]
    ) -> None:
        db, _ = full_setup
        decomposer = QueryDecomposer()
        fts = FTSIndex(db=db)
        fusion = HybridSearch()
        evidence_builder = EvidenceBuilder(db=db)

        fragments = decomposer.decompose("quantum entanglement teleportation")
        fts_hits = fts.search(fragments)
        hybrid = fusion.fuse(fts_hits, [])
        evidence = evidence_builder.build(hybrid, fragments)

        assert evidence.is_empty

    def test_evidence_has_source_paths(
        self, full_setup: tuple[sqlite3.Connection, Path]
    ) -> None:
        db, _ = full_setup
        fts = FTSIndex(db=db)
        evidence_builder = EvidenceBuilder(db=db)

        fragments = [TypedQueryFragment(text="JARVIS", language="en", query_type="keyword")]
        fts_hits = fts.search(fragments)
        fusion = HybridSearch()
        hybrid = fusion.fuse(fts_hits, [])
        evidence = evidence_builder.build(hybrid, fragments)

        for item in evidence.items:
            assert item.source_path
            assert item.citation.label
