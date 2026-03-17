"""Tests for TaskLogStore."""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from jarvis.app.bootstrap import init_database
from jarvis.app.config import JarvisConfig
from jarvis.contracts import TaskLogEntry, TaskLogStoreProtocol, TaskStatus
from jarvis.memory.task_log import TaskLogStore


class TestTaskLogStoreInMemory:
    def test_log_and_retrieve(self) -> None:
        store = TaskLogStore()
        entry = TaskLogEntry(turn_id="t1", stage="start", status=TaskStatus.RUNNING)
        store.log_entry(entry)
        entries = store.get_entries_for_turn("t1")
        assert len(entries) == 1
        assert entries[0].stage == "start"

    def test_filter_by_turn(self) -> None:
        store = TaskLogStore()
        store.log_entry(TaskLogEntry(turn_id="t1", stage="a"))
        store.log_entry(TaskLogEntry(turn_id="t2", stage="b"))
        assert len(store.get_entries_for_turn("t1")) == 1
        assert len(store.get_entries_for_turn("t2")) == 1

    def test_entries_attribute_exists(self) -> None:
        store = TaskLogStore()
        store.log_entry(TaskLogEntry(turn_id="t1", stage="x"))
        assert len(store._entries) == 1

    def test_protocol_conformance(self) -> None:
        assert isinstance(TaskLogStore(), TaskLogStoreProtocol)


class TestTaskLogStoreSQLite:
    @pytest.fixture
    def db(self, tmp_path: Path) -> sqlite3.Connection:
        config = JarvisConfig(watched_folders=[tmp_path], data_dir=tmp_path / ".jarvis")
        return init_database(config)

    def test_persists_to_db(self, db: sqlite3.Connection) -> None:
        store = TaskLogStore(db=db)
        entry = TaskLogEntry(turn_id="t1", stage="decompose", status=TaskStatus.COMPLETED, duration_ms=42.5)
        store.log_entry(entry)
        row = db.execute("SELECT stage, status, duration_ms FROM task_logs WHERE entry_id = ?", (entry.entry_id,)).fetchone()
        assert row[0] == "decompose"
        assert row[1] == "COMPLETED"
        assert row[2] == 42.5

    def test_retrieves_from_db(self, db: sqlite3.Connection) -> None:
        store = TaskLogStore(db=db)
        store.log_entry(TaskLogEntry(turn_id="t1", stage="start", status=TaskStatus.RUNNING))
        store.log_entry(TaskLogEntry(turn_id="t1", stage="end", status=TaskStatus.COMPLETED))
        store.log_entry(TaskLogEntry(turn_id="t2", stage="other"))
        store2 = TaskLogStore(db=db)
        entries = store2.get_entries_for_turn("t1")
        assert len(entries) == 2

    def test_metadata_roundtrip(self, db: sqlite3.Connection) -> None:
        store = TaskLogStore(db=db)
        entry = TaskLogEntry(turn_id="t1", stage="test", metadata={"key": "value", "count": 42})
        store.log_entry(entry)
        store2 = TaskLogStore(db=db)
        entries = store2.get_entries_for_turn("t1")
        assert entries[0].metadata["key"] == "value"
        assert entries[0].metadata["count"] == 42
