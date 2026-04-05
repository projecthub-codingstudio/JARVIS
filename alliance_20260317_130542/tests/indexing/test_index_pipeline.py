"""Tests for IndexPipeline."""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Sequence

import pytest

from jarvis.app.bootstrap import init_database
from jarvis.app.config import JarvisConfig
from jarvis.app.runtime_context import purge_documents_outside_knowledge_base
from jarvis.contracts import ChunkRecord, DocumentRecord, IndexingStatus
from jarvis.indexing.index_pipeline import IndexPipeline
from jarvis.indexing.parsers import DocumentParser
from jarvis.indexing.chunker import Chunker
from jarvis.indexing.tombstone import TombstoneManager


class FakeEmbeddingRuntime:
    """Stub embedding runtime for testing (no real model needed)."""

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        return [[0.0] * 8 for _ in texts]


class FakeVectorIndex:
    def __init__(self) -> None:
        self.removed_chunk_ids: list[str] = []
        self.removed_document_ids: list[str] = []

    def remove(self, chunk_ids: list[str]) -> None:
        self.removed_chunk_ids.extend(chunk_ids)

    def remove_document(self, document_id: str) -> None:
        self.removed_document_ids.append(document_id)


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
        f.write_text("Content that is long enough to survive minimum chunk size filtering requirements.")
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
        f.write_text("Same content repeated here to ensure it meets the minimum chunk size threshold for testing.")
        r1 = pipeline.index_file(f)
        r2 = pipeline.index_file(f)
        assert r1.document_id == r2.document_id
        count = db.execute(
            "SELECT COUNT(*) FROM chunks WHERE document_id = ?",
            (r1.document_id,),
        ).fetchone()[0]
        assert count >= 1

    def test_failed_document_with_same_hash_is_retried(
        self, pipeline: IndexPipeline, db: sqlite3.Connection, tmp_path: Path
    ) -> None:
        f = tmp_path / "doc.md"
        f.write_text("Recovered content that is long enough to survive minimum chunk size filtering requirements.")

        failed_record = DocumentParser().create_record(f)
        db.execute(
            "INSERT INTO documents (document_id, path, content_hash, size_bytes, indexing_status)"
            " VALUES (?, ?, ?, ?, ?)",
            (
                failed_record.document_id,
                failed_record.path,
                failed_record.content_hash,
                failed_record.size_bytes,
                IndexingStatus.FAILED.value,
            ),
        )
        db.commit()

        recovered = pipeline.index_file(f)

        assert recovered.document_id == failed_record.document_id
        assert recovered.indexing_status == IndexingStatus.INDEXED
        row = db.execute(
            "SELECT indexing_status FROM documents WHERE document_id = ?",
            (failed_record.document_id,),
        ).fetchone()
        assert row is not None
        assert row[0] == "INDEXED"
        chunk_count = db.execute(
            "SELECT COUNT(*) FROM chunks WHERE document_id = ?",
            (failed_record.document_id,),
        ).fetchone()[0]
        assert chunk_count >= 1

    def test_empty_document_marks_failed(
        self, pipeline: IndexPipeline, db: sqlite3.Connection, tmp_path: Path
    ) -> None:
        f = tmp_path / "empty.txt"
        f.write_text("")

        with pytest.raises(ValueError, match="no searchable content"):
            pipeline.index_file(f)

        row = db.execute(
            "SELECT indexing_status FROM documents WHERE path = ?",
            (str(f),),
        ).fetchone()
        assert row is not None
        assert row[0] == "FAILED"


class TestReindexFile:
    def test_reindex_replaces_chunks(
        self, pipeline: IndexPipeline, db: sqlite3.Connection, tmp_path: Path
    ) -> None:
        f = tmp_path / "doc.md"
        f.write_text("Original content that is long enough to survive minimum chunk size filtering requirements.")
        r1 = pipeline.index_file(f)
        old_chunks = db.execute(
            "SELECT chunk_id FROM chunks WHERE document_id = ?",
            (r1.document_id,),
        ).fetchall()

        f.write_text("Updated content with new information that also passes the minimum chunk size requirements.")
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

    def test_reindex_empty_document_marks_failed(
        self, pipeline: IndexPipeline, db: sqlite3.Connection, tmp_path: Path
    ) -> None:
        f = tmp_path / "doc.md"
        f.write_text("Original content that is long enough to survive minimum chunk size filtering requirements.")
        record = pipeline.index_file(f)

        f.write_text("")
        with pytest.raises(ValueError, match="no searchable content"):
            pipeline.reindex_file(f)

        row = db.execute(
            "SELECT indexing_status FROM documents WHERE document_id = ?",
            (record.document_id,),
        ).fetchone()
        assert row is not None
        assert row[0] == "FAILED"

    def test_reindex_prefers_document_vector_cleanup_when_available(
        self, db: sqlite3.Connection, tmp_path: Path
    ) -> None:
        vector_index = FakeVectorIndex()
        pipeline = IndexPipeline(
            db=db,
            parser=DocumentParser(),
            chunker=Chunker(max_chunk_bytes=256, overlap_bytes=32),
            tombstone_manager=TombstoneManager(db=db),
            embedding_runtime=FakeEmbeddingRuntime(),
            vector_index=vector_index,
        )
        f = tmp_path / "doc.md"
        f.write_text("Original content that is long enough to survive minimum chunk size filtering requirements.")
        record = pipeline.index_file(f)

        f.write_text("Updated content with new information that also passes the minimum chunk size requirements.")
        pipeline.reindex_file(f)

        assert vector_index.removed_document_ids == [record.document_id]
        assert vector_index.removed_chunk_ids == []


class TestRemoveFile:
    def test_remove_tombstones_document(
        self, pipeline: IndexPipeline, db: sqlite3.Connection, tmp_path: Path
    ) -> None:
        f = tmp_path / "doc.md"
        f.write_text("Content to remove that is long enough to survive minimum chunk size filtering requirements.")
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
        f.write_text("Content to remove that is long enough to survive minimum chunk size filtering requirements.")
        record = pipeline.index_file(f)
        pipeline.remove_file(f)
        count = db.execute(
            "SELECT COUNT(*) FROM chunks WHERE document_id = ?",
            (record.document_id,),
        ).fetchone()[0]
        assert count == 0


class TestKnowledgeBasePurge:
    def test_purge_documents_outside_active_knowledge_base(
        self, db: sqlite3.Connection, tmp_path: Path
    ) -> None:
        active_root = tmp_path / "knowledge_base"
        active_root.mkdir()
        outside_root = tmp_path / "other_docs"
        outside_root.mkdir()

        active_path = active_root / "inside.md"
        outside_path = outside_root / "outside.md"
        active_path.write_text("Inside knowledge base content that is long enough for chunking.")
        outside_path.write_text("Outside knowledge base content that is long enough for chunking.")

        db.execute(
            "INSERT INTO documents (document_id, path, content_hash, size_bytes, indexing_status)"
            " VALUES (?, ?, ?, ?, ?)",
            ("doc-inside", str(active_path), "h1", active_path.stat().st_size, "INDEXED"),
        )
        db.execute(
            "INSERT INTO documents (document_id, path, content_hash, size_bytes, indexing_status)"
            " VALUES (?, ?, ?, ?, ?)",
            ("doc-outside", str(outside_path), "h2", outside_path.stat().st_size, "INDEXED"),
        )
        db.execute(
            "INSERT INTO chunks (chunk_id, document_id, byte_start, byte_end, line_start, line_end, text, chunk_hash, lexical_morphs, heading_path, embedding_ref)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("chunk-inside", "doc-inside", 0, 10, 1, 1, "inside", "c1", "", "", "lance:chunk-inside"),
        )
        db.execute(
            "INSERT INTO chunks (chunk_id, document_id, byte_start, byte_end, line_start, line_end, text, chunk_hash, lexical_morphs, heading_path, embedding_ref)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("chunk-outside", "doc-outside", 0, 10, 1, 1, "outside", "c2", "", "", "lance:chunk-outside"),
        )
        db.commit()

        vector_index = FakeVectorIndex()
        removed = purge_documents_outside_knowledge_base(db, active_root, vector_index=vector_index)

        assert removed == 1
        remaining_docs = db.execute("SELECT document_id FROM documents ORDER BY document_id").fetchall()
        remaining_chunks = db.execute("SELECT chunk_id FROM chunks ORDER BY chunk_id").fetchall()
        assert remaining_docs == [("doc-inside",)]
        assert remaining_chunks == [("chunk-inside",)]
        assert vector_index.removed_chunk_ids == ["chunk-outside"]
