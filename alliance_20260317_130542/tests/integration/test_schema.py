"""Integration tests for SQLite schema initialization and DDL compatibility."""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path

import pytest


@pytest.fixture
def schema_sql() -> str:
    schema_path = Path(__file__).parent.parent.parent / "sql" / "schema.sql"
    return schema_path.read_text()


@pytest.fixture
def db(schema_sql: str) -> sqlite3.Connection:
    """Create an in-memory SQLite database with the JARVIS schema."""
    conn = sqlite3.connect(":memory:")
    conn.executescript(schema_sql)
    return conn


class TestSchemaInitialization:
    def test_schema_creates_successfully(self, db: sqlite3.Connection) -> None:
        """Phase 0 exit criterion: SQLite schema initializes successfully."""
        # Verify all 5 tables exist
        cursor = db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        tables = {row[0] for row in cursor.fetchall()}
        required = {"documents", "chunks", "citations", "conversation_turns", "task_logs"}
        assert required.issubset(tables), f"Missing tables: {required - tables}"

    def test_fts5_virtual_table_exists(self, db: sqlite3.Connection) -> None:
        cursor = db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='chunks_fts'"
        )
        assert cursor.fetchone() is not None

    def test_wal_mode(self, db: sqlite3.Connection) -> None:
        cursor = db.execute("PRAGMA journal_mode")
        mode = cursor.fetchone()[0]
        # In-memory databases may report 'memory', which is fine
        assert mode in ("wal", "memory")

    def test_foreign_keys_enabled(self, db: sqlite3.Connection) -> None:
        cursor = db.execute("PRAGMA foreign_keys")
        assert cursor.fetchone()[0] == 1


class TestDocumentsTable:
    def test_insert_and_retrieve(self, db: sqlite3.Connection) -> None:
        doc_id = str(uuid.uuid4())
        db.execute(
            "INSERT INTO documents (document_id, path, content_hash, size_bytes) "
            "VALUES (?, ?, ?, ?)",
            (doc_id, "/test/file.py", "abc123", 1024),
        )
        cursor = db.execute("SELECT * FROM documents WHERE document_id = ?", (doc_id,))
        row = cursor.fetchone()
        assert row is not None
        assert row[1] == "/test/file.py"  # path

    def test_unique_path_constraint(self, db: sqlite3.Connection) -> None:
        db.execute(
            "INSERT INTO documents (document_id, path) VALUES (?, ?)",
            (str(uuid.uuid4()), "/test/unique.py"),
        )
        with pytest.raises(sqlite3.IntegrityError):
            db.execute(
                "INSERT INTO documents (document_id, path) VALUES (?, ?)",
                (str(uuid.uuid4()), "/test/unique.py"),
            )

    def test_indexing_status_check(self, db: sqlite3.Connection) -> None:
        with pytest.raises(sqlite3.IntegrityError):
            db.execute(
                "INSERT INTO documents (document_id, path, indexing_status) VALUES (?, ?, ?)",
                (str(uuid.uuid4()), "/test/bad.py", "INVALID_STATUS"),
            )

    def test_access_status_check(self, db: sqlite3.Connection) -> None:
        with pytest.raises(sqlite3.IntegrityError):
            db.execute(
                "INSERT INTO documents (document_id, path, access_status) VALUES (?, ?, ?)",
                (str(uuid.uuid4()), "/test/bad.py", "WRONG"),
            )


class TestChunksTable:
    def test_insert_with_fk(self, db: sqlite3.Connection) -> None:
        doc_id = str(uuid.uuid4())
        chunk_id = str(uuid.uuid4())
        db.execute(
            "INSERT INTO documents (document_id, path) VALUES (?, ?)",
            (doc_id, "/test/file.py"),
        )
        db.execute(
            "INSERT INTO chunks (chunk_id, document_id, text, chunk_hash) VALUES (?, ?, ?, ?)",
            (chunk_id, doc_id, "def hello():\n    pass", "hash123"),
        )
        cursor = db.execute("SELECT text FROM chunks WHERE chunk_id = ?", (chunk_id,))
        assert cursor.fetchone()[0] == "def hello():\n    pass"

    def test_fts5_search(self, db: sqlite3.Connection) -> None:
        doc_id = str(uuid.uuid4())
        db.execute(
            "INSERT INTO documents (document_id, path) VALUES (?, ?)",
            (doc_id, "/test/search.py"),
        )
        db.execute(
            "INSERT INTO chunks (chunk_id, document_id, text) VALUES (?, ?, ?)",
            (str(uuid.uuid4()), doc_id, "프로젝트 관리 시스템의 아키텍처 설계"),
        )
        db.execute(
            "INSERT INTO chunks (chunk_id, document_id, text) VALUES (?, ?, ?)",
            (str(uuid.uuid4()), doc_id, "def calculate_metrics(): return 42"),
        )
        db.commit()

        # FTS5 search for Korean text
        cursor = db.execute(
            "SELECT text FROM chunks_fts WHERE chunks_fts MATCH '아키텍처'"
        )
        results = cursor.fetchall()
        assert len(results) >= 1

    def test_cascade_delete(self, db: sqlite3.Connection) -> None:
        doc_id = str(uuid.uuid4())
        chunk_id = str(uuid.uuid4())
        db.execute(
            "INSERT INTO documents (document_id, path) VALUES (?, ?)",
            (doc_id, "/test/cascade.py"),
        )
        db.execute(
            "INSERT INTO chunks (chunk_id, document_id, text) VALUES (?, ?, ?)",
            (chunk_id, doc_id, "some text"),
        )
        db.execute("DELETE FROM documents WHERE document_id = ?", (doc_id,))
        cursor = db.execute("SELECT * FROM chunks WHERE chunk_id = ?", (chunk_id,))
        assert cursor.fetchone() is None


class TestCitationsTable:
    def test_insert_citation(self, db: sqlite3.Connection) -> None:
        doc_id = str(uuid.uuid4())
        chunk_id = str(uuid.uuid4())
        cit_id = str(uuid.uuid4())
        db.execute("INSERT INTO documents (document_id, path) VALUES (?, ?)",
                    (doc_id, "/test/cite.py"))
        db.execute("INSERT INTO chunks (chunk_id, document_id, text) VALUES (?, ?, ?)",
                    (chunk_id, doc_id, "text"))
        db.execute(
            "INSERT INTO citations (citation_id, document_id, chunk_id, label, state) "
            "VALUES (?, ?, ?, ?, ?)",
            (cit_id, doc_id, chunk_id, "[1]", "VALID"),
        )
        cursor = db.execute("SELECT state FROM citations WHERE citation_id = ?", (cit_id,))
        assert cursor.fetchone()[0] == "VALID"

    def test_citation_state_check(self, db: sqlite3.Connection) -> None:
        doc_id = str(uuid.uuid4())
        chunk_id = str(uuid.uuid4())
        db.execute("INSERT INTO documents (document_id, path) VALUES (?, ?)",
                    (doc_id, "/test/cite2.py"))
        db.execute("INSERT INTO chunks (chunk_id, document_id, text) VALUES (?, ?, ?)",
                    (chunk_id, doc_id, "text"))
        with pytest.raises(sqlite3.IntegrityError):
            db.execute(
                "INSERT INTO citations (citation_id, document_id, chunk_id, state) "
                "VALUES (?, ?, ?, ?)",
                (str(uuid.uuid4()), doc_id, chunk_id, "INVALID"),
            )


class TestConversationTurnsTable:
    def test_insert_turn(self, db: sqlite3.Connection) -> None:
        turn_id = str(uuid.uuid4())
        db.execute(
            "INSERT INTO conversation_turns (turn_id, user_input, assistant_output, has_evidence) "
            "VALUES (?, ?, ?, ?)",
            (turn_id, "질문입니다", "답변입니다", 1),
        )
        cursor = db.execute("SELECT * FROM conversation_turns WHERE turn_id = ?", (turn_id,))
        row = cursor.fetchone()
        assert row[1] == "질문입니다"
        assert row[3] == 1  # has_evidence


class TestTaskLogsTable:
    def test_insert_log(self, db: sqlite3.Connection) -> None:
        entry_id = str(uuid.uuid4())
        turn_id = str(uuid.uuid4())
        metadata = json.dumps({"model": "test-14b"})
        db.execute(
            "INSERT INTO task_logs (entry_id, turn_id, stage, status, duration_ms, metadata) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (entry_id, turn_id, "retrieval", "COMPLETED", 150.5, metadata),
        )
        cursor = db.execute("SELECT * FROM task_logs WHERE entry_id = ?", (entry_id,))
        row = cursor.fetchone()
        assert row[2] == "retrieval"
        assert row[5] == 150.5

    def test_status_check(self, db: sqlite3.Connection) -> None:
        with pytest.raises(sqlite3.IntegrityError):
            db.execute(
                "INSERT INTO task_logs (entry_id, turn_id, stage, status) "
                "VALUES (?, ?, ?, ?)",
                (str(uuid.uuid4()), "t1", "test", "BOGUS"),
            )
