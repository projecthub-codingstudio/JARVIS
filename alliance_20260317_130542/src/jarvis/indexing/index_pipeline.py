"""IndexPipeline — orchestrates parse, chunk, embed, and index operations.

Processes file change events from the FileWatcher and updates both
the FTS and vector indexes.
"""
from __future__ import annotations

import sqlite3
from dataclasses import replace
from pathlib import Path

from jarvis.contracts import ChunkRecord, DocumentRecord, EmbeddingRuntimeProtocol, IndexingStatus
from jarvis.indexing.chunker import Chunker
from jarvis.indexing.parsers import DocumentParser
from jarvis.indexing.tombstone import TombstoneManager


class IndexPipeline:
    """Full indexing pipeline: parse -> chunk -> embed -> store."""

    def __init__(
        self,
        *,
        db: sqlite3.Connection,
        parser: DocumentParser,
        chunker: Chunker,
        tombstone_manager: TombstoneManager,
        embedding_runtime: EmbeddingRuntimeProtocol,
    ) -> None:
        self._db = db
        self._parser = parser
        self._chunker = chunker
        self._tombstone = tombstone_manager
        self._embedding_runtime = embedding_runtime

    def _find_document_by_path(self, path: Path) -> DocumentRecord | None:
        row = self._db.execute(
            "SELECT document_id, path, content_hash, size_bytes, indexing_status"
            " FROM documents WHERE path = ?",
            (str(path),),
        ).fetchone()
        if row is None:
            return None
        return DocumentRecord(
            document_id=row[0],
            path=row[1],
            content_hash=row[2],
            size_bytes=row[3],
            indexing_status=IndexingStatus(row[4]),
        )

    def _write_document(self, record: DocumentRecord) -> None:
        self._db.execute(
            "INSERT INTO documents"
            " (document_id, path, content_hash, size_bytes, indexing_status)"
            " VALUES (?, ?, ?, ?, ?)"
            " ON CONFLICT(document_id) DO UPDATE SET"
            " content_hash = excluded.content_hash,"
            " size_bytes = excluded.size_bytes,"
            " indexing_status = excluded.indexing_status,"
            " updated_at = datetime('now')",
            (
                record.document_id,
                record.path,
                record.content_hash,
                record.size_bytes,
                record.indexing_status.value,
            ),
        )

    def _delete_chunks(self, document_id: str) -> None:
        self._db.execute(
            "DELETE FROM chunks WHERE document_id = ?",
            (document_id,),
        )

    def _insert_chunks(self, chunks: list[ChunkRecord]) -> None:
        """Insert chunks immediately without morpheme analysis.

        Per Spec Task 1.1: metadata first, morphemes later via deferred queue.
        FTS5 triggers fire on INSERT, so raw text is searchable immediately.
        """
        for chunk in chunks:
            self._db.execute(
                "INSERT INTO chunks"
                " (chunk_id, document_id, byte_start, byte_end, line_start, line_end,"
                "  text, chunk_hash, lexical_morphs, heading_path)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    chunk.chunk_id,
                    chunk.document_id,
                    chunk.byte_start,
                    chunk.byte_end,
                    chunk.line_start,
                    chunk.line_end,
                    chunk.text,
                    chunk.chunk_hash,
                    "",  # morphs deferred
                    chunk.heading_path,
                ),
            )

    def backfill_morphemes(self, *, batch_size: int = 100) -> int:
        """Backfill lexical_morphs for chunks that don't have them yet.

        Per Spec Task 1.1: "same file change updates metadata first
        and embeddings later via deferred queue."

        Returns the number of chunks updated.
        """
        from jarvis.retrieval.tokenizer_kiwi import KiwiTokenizer

        if not hasattr(self, "_kiwi"):
            self._kiwi = KiwiTokenizer()

        rows = self._db.execute(
            "SELECT chunk_id, text FROM chunks"
            " WHERE lexical_morphs = '' LIMIT ?",
            (batch_size,),
        ).fetchall()

        updated = 0
        for chunk_id, text in rows:
            morphs = self._kiwi.tokenize_for_fts(text[:2000])
            if morphs:
                self._db.execute(
                    "UPDATE chunks SET lexical_morphs = ? WHERE chunk_id = ?",
                    (morphs, chunk_id),
                )
                updated += 1

        if updated:
            self._db.commit()
        return updated

    def index_file(self, path: Path) -> DocumentRecord:
        record = self._parser.create_record(path)

        # Check if already indexed with same hash
        existing = self._find_document_by_path(path)
        if existing and existing.content_hash == record.content_hash:
            return existing

        # Reuse document_id if path already exists
        if existing:
            record = replace(record, document_id=existing.document_id)
            self._delete_chunks(existing.document_id)

        # Parse and chunk
        text = self._parser.parse(path)
        chunks = self._chunker.chunk(text, document_id=record.document_id)

        # Write document as INDEXING
        record = replace(record, indexing_status=IndexingStatus.INDEXING)
        self._write_document(record)

        # Write chunks
        self._insert_chunks(chunks)

        # Mark as INDEXED
        record = replace(record, indexing_status=IndexingStatus.INDEXED)
        self._write_document(record)
        self._db.commit()

        return record

    def reindex_file(self, path: Path) -> DocumentRecord:
        record = self._parser.create_record(path)

        existing = self._find_document_by_path(path)
        if existing:
            record = replace(record, document_id=existing.document_id)
            self._delete_chunks(existing.document_id)

        text = self._parser.parse(path)
        chunks = self._chunker.chunk(text, document_id=record.document_id)

        record = replace(record, indexing_status=IndexingStatus.INDEXING)
        self._write_document(record)
        self._insert_chunks(chunks)
        record = replace(record, indexing_status=IndexingStatus.INDEXED)
        self._write_document(record)
        self._db.commit()

        return record

    def remove_file(self, path: Path) -> None:
        existing = self._find_document_by_path(path)
        if existing is None:
            return
        self._delete_chunks(existing.document_id)
        self._tombstone.create_tombstone(existing)
