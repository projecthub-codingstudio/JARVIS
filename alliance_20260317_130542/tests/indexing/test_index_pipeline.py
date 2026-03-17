"""Tests for IndexPipeline."""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Sequence

import pytest

from jarvis.app.bootstrap import init_database
from jarvis.app.config import JarvisConfig
from jarvis.contracts import ChunkRecord, DocumentRecord, IndexingStatus
from jarvis.indexing.index_pipeline import IndexPipeline
from jarvis.indexing.parsers import DocumentParser
from jarvis.indexing.chunker import Chunker
from jarvis.indexing.tombstone import TombstoneManager


class FakeEmbeddingRuntime:
    """Stub embedding runtime for testing (no real model needed)."""

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        return [[0.0] * 8 for _ in texts]


@pytest.fixture
def db(tmp_path: Path) -> sqlite3.Connection:
    config = JarvisConfig(watched_folders=[tmp_path], data_dir=tmp_path / ".jarvis")
    return init_database(config)


@pytest.fixture
def pipeline(db: sqlite3.Connection) -> IndexPipeline:
    return IndexPipeline(
        db=db,
        parser=DocumentParser(),
        chunker=Chunker(max_chunk_bytes=256, overlap_bytes=32),
        tombstone_manager=TombstoneManager(db=db),
        embedding_runtime=FakeEmbeddingRuntime(),
    )


class TestIndexFile:
    def test_index_markdown(self, pipeline: IndexPipeline, tmp_path: Path) -> None:
        f = tmp_path / "doc.md"
        f.write_text("# Title\n\nSome paragraph content for indexing.")
        record = pipeline.index_file(f)
        assert isinstance(record, DocumentRecord)
        assert record.indexing_status == IndexingStatus.INDEXED
        assert record.path == str(f)

    def test_index_writes_to_documents_table(
        self, pipeline: IndexPipeline, db: sqlite3.Connection, tmp_path: Path
    ) -> None:
        f = tmp_path / "doc.md"
        f.write_text("Content")
        record = pipeline.index_file(f)
        row = db.execute(
            "SELECT document_id, path, indexing_status FROM documents WHERE document_id = ?",
            (record.document_id,),
        ).fetchone()
        assert row is not None
        assert row[1] == str(f)
        assert row[2] == "INDEXED"

    def test_index_writes_chunks(
        self, pipeline: IndexPipeline, db: sqlite3.Connection, tmp_path: Path
    ) -> None:
        f = tmp_path / "doc.md"
        f.write_text("Some content\n" * 10)
        record = pipeline.index_file(f)
        rows = db.execute(
            "SELECT chunk_id, text FROM chunks WHERE document_id = ?",
            (record.document_id,),
        ).fetchall()
        assert len(rows) >= 1
        assert rows[0][1]  # non-empty text

    def test_index_populates_fts(
        self, pipeline: IndexPipeline, db: sqlite3.Connection, tmp_path: Path
    ) -> None:
        f = tmp_path / "doc.md"
        f.write_text("JARVIS architecture design document")
        pipeline.index_file(f)
        fts_rows = db.execute(
            "SELECT * FROM chunks_fts WHERE chunks_fts MATCH ?",
            ("architecture",),
        ).fetchall()
        assert len(fts_rows) >= 1

    def test_index_nonexistent_file_raises(self, pipeline: IndexPipeline) -> None:
        with pytest.raises(FileNotFoundError):
            pipeline.index_file(Path("/nonexistent/file.md"))

    def test_duplicate_index_same_hash_is_noop(
        self, pipeline: IndexPipeline, db: sqlite3.Connection, tmp_path: Path
    ) -> None:
        f = tmp_path / "doc.md"
        f.write_text("same content")
        r1 = pipeline.index_file(f)
        r2 = pipeline.index_file(f)
        assert r1.document_id == r2.document_id
        count = db.execute(
            "SELECT COUNT(*) FROM chunks WHERE document_id = ?",
            (r1.document_id,),
        ).fetchone()[0]
        assert count >= 1


class TestReindexFile:
    def test_reindex_replaces_chunks(
        self, pipeline: IndexPipeline, db: sqlite3.Connection, tmp_path: Path
    ) -> None:
        f = tmp_path / "doc.md"
        f.write_text("Original content")
        r1 = pipeline.index_file(f)
        old_chunks = db.execute(
            "SELECT chunk_id FROM chunks WHERE document_id = ?",
            (r1.document_id,),
        ).fetchall()

        f.write_text("Updated content with new information")
        r2 = pipeline.reindex_file(f)
        assert r2.document_id == r1.document_id
        assert r2.indexing_status == IndexingStatus.INDEXED

        new_chunks = db.execute(
            "SELECT chunk_id, text FROM chunks WHERE document_id = ?",
            (r2.document_id,),
        ).fetchall()
        old_ids = {r[0] for r in old_chunks}
        new_ids = {r[0] for r in new_chunks}
        assert old_ids != new_ids
        assert "Updated" in new_chunks[0][1]


class TestRemoveFile:
    def test_remove_tombstones_document(
        self, pipeline: IndexPipeline, db: sqlite3.Connection, tmp_path: Path
    ) -> None:
        f = tmp_path / "doc.md"
        f.write_text("Content to remove")
        record = pipeline.index_file(f)
        pipeline.remove_file(f)
        row = db.execute(
            "SELECT indexing_status FROM documents WHERE document_id = ?",
            (record.document_id,),
        ).fetchone()
        assert row[0] == "TOMBSTONED"

    def test_remove_deletes_chunks(
        self, pipeline: IndexPipeline, db: sqlite3.Connection, tmp_path: Path
    ) -> None:
        f = tmp_path / "doc.md"
        f.write_text("Content to remove")
        record = pipeline.index_file(f)
        pipeline.remove_file(f)
        count = db.execute(
            "SELECT COUNT(*) FROM chunks WHERE document_id = ?",
            (record.document_id,),
        ).fetchone()[0]
        assert count == 0
