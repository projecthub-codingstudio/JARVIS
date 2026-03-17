"""Tests for TombstoneManager."""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from jarvis.app.bootstrap import init_database
from jarvis.app.config import JarvisConfig
from jarvis.contracts import DocumentRecord, IndexingStatus
from jarvis.indexing.tombstone import TombstoneManager


@pytest.fixture
def db(tmp_path: Path) -> sqlite3.Connection:
    config = JarvisConfig(watched_folders=[tmp_path], data_dir=tmp_path / ".jarvis")
    return init_database(config)


@pytest.fixture
def manager(db: sqlite3.Connection) -> TombstoneManager:
    return TombstoneManager(db=db)


def _insert_doc(db: sqlite3.Connection, doc: DocumentRecord) -> None:
    db.execute(
        "INSERT INTO documents (document_id, path, content_hash, size_bytes, indexing_status)"
        " VALUES (?, ?, ?, ?, ?)",
        (doc.document_id, doc.path, doc.content_hash, doc.size_bytes, doc.indexing_status.value),
    )
    db.commit()


class TestTombstoneManager:
    def test_create_tombstone(self, db: sqlite3.Connection, manager: TombstoneManager) -> None:
        doc = DocumentRecord(path="/tmp/gone.md", content_hash="abc", indexing_status=IndexingStatus.INDEXED)
        _insert_doc(db, doc)
        result = manager.create_tombstone(doc)
        assert result.indexing_status == IndexingStatus.TOMBSTONED
        row = db.execute(
            "SELECT indexing_status FROM documents WHERE document_id = ?",
            (doc.document_id,),
        ).fetchone()
        assert row[0] == "TOMBSTONED"

    def test_is_tombstoned_true(self, db: sqlite3.Connection, manager: TombstoneManager) -> None:
        doc = DocumentRecord(path="/tmp/gone.md", content_hash="abc", indexing_status=IndexingStatus.INDEXED)
        _insert_doc(db, doc)
        manager.create_tombstone(doc)
        assert manager.is_tombstoned(doc.document_id) is True

    def test_is_tombstoned_false(self, db: sqlite3.Connection, manager: TombstoneManager) -> None:
        doc = DocumentRecord(path="/tmp/alive.md", content_hash="abc", indexing_status=IndexingStatus.INDEXED)
        _insert_doc(db, doc)
        assert manager.is_tombstoned(doc.document_id) is False

    def test_is_tombstoned_missing_id(self, manager: TombstoneManager) -> None:
        assert manager.is_tombstoned("nonexistent-id") is False

    def test_list_tombstones(self, db: sqlite3.Connection, manager: TombstoneManager) -> None:
        for i in range(3):
            doc = DocumentRecord(path=f"/tmp/file{i}.md", content_hash=f"h{i}", indexing_status=IndexingStatus.INDEXED)
            _insert_doc(db, doc)
            manager.create_tombstone(doc)
        alive = DocumentRecord(path="/tmp/alive.md", content_hash="ha", indexing_status=IndexingStatus.INDEXED)
        _insert_doc(db, alive)
        tombstones = manager.list_tombstones()
        assert len(tombstones) == 3
        for t in tombstones:
            assert t.indexing_status == IndexingStatus.TOMBSTONED

    def test_list_tombstones_empty(self, manager: TombstoneManager) -> None:
        assert manager.list_tombstones() == []
