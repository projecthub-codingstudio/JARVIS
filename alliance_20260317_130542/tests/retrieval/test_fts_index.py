"""Tests for FTSIndex."""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Sequence

import pytest

from jarvis.app.bootstrap import init_database
from jarvis.app.config import JarvisConfig
from jarvis.contracts import SearchHit, TypedQueryFragment
from jarvis.indexing.chunker import Chunker
from jarvis.indexing.index_pipeline import IndexPipeline
from jarvis.indexing.parsers import DocumentParser
from jarvis.indexing.tombstone import TombstoneManager
from jarvis.retrieval.fts_index import FTSIndex


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
    (tmp_path / "arch.md").write_text(
        "# JARVIS Architecture\n\nThe system uses a monolith-first design with protocol interfaces."
    )
    (tmp_path / "korean.md").write_text(
        "# JARVIS 프로젝트\n\n음성 인식 시스템의 아키텍처를 설명합니다."
    )
    (tmp_path / "code.py").write_text(
        '"""Search module."""\n\ndef search_files(query: str) -> list:\n    pass\n'
    )
    pipeline.index_file(tmp_path / "arch.md")
    pipeline.index_file(tmp_path / "korean.md")
    pipeline.index_file(tmp_path / "code.py")
    return db


class TestFTSIndexNoDb:
    def test_returns_empty_without_db(self) -> None:
        fts = FTSIndex()
        fragments = [TypedQueryFragment(text="test", language="en", query_type="keyword")]
        hits = fts.search(fragments)
        assert hits == []


class TestFTSIndexWithDb:
    def test_search_english(self, indexed_db: sqlite3.Connection) -> None:
        fts = FTSIndex(db=indexed_db)
        fragments = [TypedQueryFragment(text="architecture", language="en", query_type="keyword")]
        hits = fts.search(fragments)
        assert len(hits) >= 1

    def test_search_korean(self, indexed_db: sqlite3.Connection) -> None:
        fts = FTSIndex(db=indexed_db)
        fragments = [TypedQueryFragment(text="음성 인식", language="ko", query_type="keyword")]
        hits = fts.search(fragments)
        assert len(hits) >= 1

    def test_search_no_results(self, indexed_db: sqlite3.Connection) -> None:
        fts = FTSIndex(db=indexed_db)
        fragments = [TypedQueryFragment(text="xyznonexistent", language="en", query_type="keyword")]
        hits = fts.search(fragments)
        assert hits == []

    def test_search_respects_top_k(self, indexed_db: sqlite3.Connection) -> None:
        fts = FTSIndex(db=indexed_db)
        fragments = [TypedQueryFragment(text="JARVIS", language="en", query_type="keyword")]
        hits = fts.search(fragments, top_k=1)
        assert len(hits) <= 1

    def test_hits_have_byte_ranges(self, indexed_db: sqlite3.Connection) -> None:
        fts = FTSIndex(db=indexed_db)
        fragments = [TypedQueryFragment(text="monolith", language="en", query_type="keyword")]
        hits = fts.search(fragments)
        if hits:
            assert hits[0].byte_range is not None
            assert hits[0].line_range is not None

    def test_multiple_fragments(self, indexed_db: sqlite3.Connection) -> None:
        fts = FTSIndex(db=indexed_db)
        fragments = [
            TypedQueryFragment(text="architecture", language="en", query_type="keyword"),
            TypedQueryFragment(text="design", language="en", query_type="keyword"),
        ]
        hits = fts.search(fragments)
        assert len(hits) >= 1
