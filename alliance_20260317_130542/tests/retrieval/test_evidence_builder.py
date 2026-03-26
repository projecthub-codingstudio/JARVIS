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
    def test_returns_empty_without_db(self) -> None:
        builder = EvidenceBuilder()
        results = [HybridSearchResult(chunk_id="c1", document_id="d1", rrf_score=0.5, snippet="text")]
        fragments = [TypedQueryFragment(text="q", language="ko", query_type="keyword")]
        evidence = builder.build(results, fragments)
        assert evidence.is_empty

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

    def test_prefers_code_sources_for_source_and_class_queries(self, tmp_path: Path) -> None:
        config = JarvisConfig(watched_folders=[tmp_path], data_dir=tmp_path / ".jarvis")
        db = init_database(config)
        pipeline = IndexPipeline(
            db=db, parser=DocumentParser(),
            chunker=Chunker(max_chunk_bytes=512, overlap_bytes=64),
            tombstone_manager=TombstoneManager(db=db),
            embedding_runtime=FakeEmbeddingRuntime(),
        )
        code_path = tmp_path / "pipeline.py"
        code_path.write_text(
            "class Pipeline:\n    def run(self) -> None:\n        pass\n",
            encoding="utf-8",
        )
        doc_path = tmp_path / "guide.md"
        doc_path.write_text(
            "Pipeline 클래스는 전체 흐름을 설명하는 개념 문서입니다.\n",
            encoding="utf-8",
        )
        code_record = pipeline.index_file(code_path)
        doc_record = pipeline.index_file(doc_path)
        code_chunk_id = db.execute(
            "SELECT chunk_id FROM chunks WHERE document_id = ?",
            (code_record.document_id,),
        ).fetchone()[0]
        doc_chunk_id = db.execute(
            "SELECT chunk_id FROM chunks WHERE document_id = ?",
            (doc_record.document_id,),
        ).fetchone()[0]

        builder = EvidenceBuilder(db=db)
        results = [
            HybridSearchResult(chunk_id=doc_chunk_id, document_id=doc_record.document_id, rrf_score=0.62),
            HybridSearchResult(chunk_id=code_chunk_id, document_id=code_record.document_id, rrf_score=0.55),
        ]
        fragments = [
            TypedQueryFragment(
                text="파이선 소스 pipeline.py Pipeline class source",
                language="mixed",
                query_type="keyword",
            )
        ]

        evidence = builder.build(results, fragments)

        assert evidence.items[0].source_path.endswith("pipeline.py")

    def test_prefers_explanatory_document_chunk_over_cross_reference(self, tmp_path: Path) -> None:
        config = JarvisConfig(watched_folders=[tmp_path], data_dir=tmp_path / ".jarvis")
        db = init_database(config)
        db.execute(
            "INSERT INTO documents (document_id, path, content_hash, size_bytes, indexing_status) VALUES (?, ?, ?, ?, ?)",
            ("doc-hwp", str(tmp_path / "hwp-format.txt"), "hash", 100, "INDEXED"),
        )
        db.execute(
            "INSERT INTO chunks (chunk_id, document_id, text, chunk_hash, heading_path) VALUES (?, ?, ?, ?, ?)",
            (
                "chunk-ref",
                "doc-hwp",
                "자세한 것은 그리기 개체 자료 구조를 참조하기 바란다. 그리기 개체가 아닐 때는 하이퍼 텍스트 정보가 포함되어 있다.",
                "hash-ref",
                "section-reference",
            ),
        )
        db.execute(
            "INSERT INTO chunks (chunk_id, document_id, text, chunk_hash, heading_path) VALUES (?, ?, ?, ?, ?)",
            (
                "chunk-body",
                "doc-hwp",
                "그리기 개체 자료 구조 기본 구조 그리기 개체는 여러 개의 개체를 하나의 틀로 묶을 수 있기 때문에, 하나의 그림 코드에 하나 이상의 개체가 존재할 수 있다. 파일상에는 다음과 같은 구조로 저장된다.",
                "hash-body",
                "section-body",
            ),
        )
        db.commit()

        builder = EvidenceBuilder(db=db)
        results = [
            HybridSearchResult(chunk_id="chunk-ref", document_id="doc-hwp", rrf_score=0.62),
            HybridSearchResult(chunk_id="chunk-body", document_id="doc-hwp", rrf_score=0.58),
        ]
        fragments = [
            TypedQueryFragment(
                text="한글 문서 형식에서 그리기 개체 자료 구조 중 기본 구조에 대해 설명해 주세요",
                language="ko",
                query_type="keyword",
            )
        ]

        evidence = builder.build(results, fragments)

        assert evidence.items[0].chunk_id == "chunk-body"
