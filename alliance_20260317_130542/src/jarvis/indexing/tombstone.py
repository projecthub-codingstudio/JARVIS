"""Tombstone — manages soft-deletion records for removed documents.

When a file is deleted or access is lost, a tombstone is created
so that stale citations can be properly flagged rather than silently
returning invalid results.
"""
from __future__ import annotations

import sqlite3
from dataclasses import replace

from jarvis.contracts import DocumentRecord, IndexingStatus


class TombstoneManager:
    """Manages tombstone records for deleted/inaccessible documents."""

    def __init__(self, *, db: sqlite3.Connection) -> None:
        self._db = db

    def create_tombstone(self, document: DocumentRecord) -> DocumentRecord:
        self._db.execute(
            "UPDATE documents SET indexing_status = ?, updated_at = datetime('now')"
            " WHERE document_id = ?",
            (IndexingStatus.TOMBSTONED.value, document.document_id),
        )
        self._db.commit()
        return replace(document, indexing_status=IndexingStatus.TOMBSTONED)

    def is_tombstoned(self, document_id: str) -> bool:
        row = self._db.execute(
            "SELECT indexing_status FROM documents WHERE document_id = ?",
            (document_id,),
        ).fetchone()
        if row is None:
            return False
        return row[0] == IndexingStatus.TOMBSTONED.value

    def list_tombstones(self) -> list[DocumentRecord]:
        rows = self._db.execute(
            "SELECT document_id, path, content_hash, size_bytes, indexing_status"
            " FROM documents WHERE indexing_status = ?",
            (IndexingStatus.TOMBSTONED.value,),
        ).fetchall()
        return [
            DocumentRecord(
                document_id=r[0],
                path=r[1],
                content_hash=r[2],
                size_bytes=r[3],
                indexing_status=IndexingStatus(r[4]),
            )
            for r in rows
        ]
