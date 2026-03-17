"""Integration test: full indexing round-trip from file to FTS search."""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Sequence

import pytest

from jarvis.app.bootstrap import init_database
from jarvis.app.config import JarvisConfig
from jarvis.indexing.chunker import Chunker
from jarvis.indexing.index_pipeline import IndexPipeline
from jarvis.indexing.parsers import DocumentParser
from jarvis.indexing.tombstone import TombstoneManager


class FakeEmbeddingRuntime:
    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        return [[0.0] * 8 for _ in texts]


@pytest.fixture
def setup(tmp_path: Path) -> tuple[IndexPipeline, sqlite3.Connection, Path]:
    config = JarvisConfig(watched_folders=[tmp_path], data_dir=tmp_path / ".jarvis")
    db = init_database(config)
    pipeline = IndexPipeline(
        db=db,
        parser=DocumentParser(),
        chunker=Chunker(max_chunk_bytes=512, overlap_bytes=64),
        tombstone_manager=TombstoneManager(db=db),
        embedding_runtime=FakeEmbeddingRuntime(),
    )
    return pipeline, db, tmp_path


@pytest.mark.integration
class TestIndexingRoundTrip:
    def test_index_and_fts_search(
        self, setup: tuple[IndexPipeline, sqlite3.Connection, Path]
    ) -> None:
        pipeline, db, tmp_path = setup

        (tmp_path / "arch.md").write_text(
            "# JARVIS Architecture\n\nThe system uses a monolith-first design with protocol interfaces."
        )
        (tmp_path / "retrieval.py").write_text(
            '"""Retrieval module for JARVIS."""\n\ndef search(query: str) -> list:\n    pass\n'
        )

        r1 = pipeline.index_file(tmp_path / "arch.md")
        r2 = pipeline.index_file(tmp_path / "retrieval.py")

        rows = db.execute(
            "SELECT c.chunk_id, c.document_id, c.text"
            " FROM chunks c"
            " JOIN chunks_fts f ON c.rowid = f.rowid"
            " WHERE chunks_fts MATCH ?",
            ("architecture",),
        ).fetchall()
        assert len(rows) >= 1
        assert any("Architecture" in r[2] for r in rows)

        rows_mono = db.execute(
            "SELECT c.text FROM chunks c"
            " JOIN chunks_fts f ON c.rowid = f.rowid"
            " WHERE chunks_fts MATCH ?",
            ("monolith",),
        ).fetchall()
        assert len(rows_mono) >= 1

    def test_reindex_updates_fts(
        self, setup: tuple[IndexPipeline, sqlite3.Connection, Path]
    ) -> None:
        pipeline, db, tmp_path = setup

        f = tmp_path / "doc.md"
        f.write_text("Original topic about databases")
        pipeline.index_file(f)

        assert db.execute(
            "SELECT COUNT(*) FROM chunks_fts WHERE chunks_fts MATCH ?",
            ("databases",),
        ).fetchone()[0] >= 1

        f.write_text("Updated topic about networking")
        pipeline.reindex_file(f)

        assert db.execute(
            "SELECT COUNT(*) FROM chunks_fts WHERE chunks_fts MATCH ?",
            ("databases",),
        ).fetchone()[0] == 0

        assert db.execute(
            "SELECT COUNT(*) FROM chunks_fts WHERE chunks_fts MATCH ?",
            ("networking",),
        ).fetchone()[0] >= 1

    def test_remove_clears_fts(
        self, setup: tuple[IndexPipeline, sqlite3.Connection, Path]
    ) -> None:
        pipeline, db, tmp_path = setup

        f = tmp_path / "ephemeral.md"
        f.write_text("Ephemeral content for deletion test")
        pipeline.index_file(f)

        assert db.execute(
            "SELECT COUNT(*) FROM chunks_fts WHERE chunks_fts MATCH ?",
            ("ephemeral",),
        ).fetchone()[0] >= 1

        pipeline.remove_file(f)

        assert db.execute(
            "SELECT COUNT(*) FROM chunks_fts WHERE chunks_fts MATCH ?",
            ("ephemeral",),
        ).fetchone()[0] == 0

    def test_index_korean_document(
        self, setup: tuple[IndexPipeline, sqlite3.Connection, Path]
    ) -> None:
        pipeline, db, tmp_path = setup

        f = tmp_path / "korean.md"
        f.write_text("# JARVIS 프로젝트\n\n음성 인식 시스템의 아키텍처를 설명합니다.")
        pipeline.index_file(f)

        chunks = db.execute("SELECT text FROM chunks").fetchall()
        assert len(chunks) >= 1
        assert any("음성" in c[0] for c in chunks)

    def test_index_test_corpus(
        self, setup: tuple[IndexPipeline, sqlite3.Connection, Path]
    ) -> None:
        """Index all files from the test corpus fixture."""
        pipeline, db, _ = setup
        corpus_dir = Path(__file__).parent.parent / "fixtures" / "corpus"
        if not corpus_dir.exists():
            pytest.skip("Test corpus not found")

        for f in corpus_dir.iterdir():
            if f.is_file() and not f.name.startswith("."):
                pipeline.index_file(f)

        doc_count = db.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
        chunk_count = db.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
        assert doc_count >= 1
        assert chunk_count >= 1
