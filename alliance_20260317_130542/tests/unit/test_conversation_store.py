"""Tests for ConversationStore."""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from jarvis.app.bootstrap import init_database
from jarvis.app.config import JarvisConfig
from jarvis.contracts import ConversationStoreProtocol, ConversationTurn
from jarvis.memory.conversation_store import ConversationStore


class TestConversationStoreInMemory:
    def test_save_and_retrieve(self) -> None:
        store = ConversationStore()
        turn = ConversationTurn(user_input="hello", assistant_output="hi")
        store.save_turn(turn)
        turns = store.get_recent_turns()
        assert len(turns) == 1
        assert turns[0].user_input == "hello"

    def test_limit(self) -> None:
        store = ConversationStore()
        for i in range(5):
            store.save_turn(ConversationTurn(user_input=f"q{i}"))
        assert len(store.get_recent_turns(limit=3)) == 3

    def test_protocol_conformance(self) -> None:
        assert isinstance(ConversationStore(), ConversationStoreProtocol)


class TestConversationStoreSQLite:
    @pytest.fixture
    def db(self, tmp_path: Path) -> sqlite3.Connection:
        config = JarvisConfig(watched_folders=[tmp_path], data_dir=tmp_path / ".jarvis")
        return init_database(config)

    def test_persists_to_db(self, db: sqlite3.Connection) -> None:
        store = ConversationStore(db=db)
        turn = ConversationTurn(user_input="test query", assistant_output="test answer", has_evidence=True)
        store.save_turn(turn)
        row = db.execute("SELECT user_input, has_evidence FROM conversation_turns WHERE turn_id = ?", (turn.turn_id,)).fetchone()
        assert row[0] == "test query"
        assert row[1] == 1

    def test_retrieves_from_db(self, db: sqlite3.Connection) -> None:
        store = ConversationStore(db=db)
        for i in range(3):
            store.save_turn(ConversationTurn(user_input=f"q{i}", assistant_output=f"a{i}"))
        # New store instance reads from DB
        store2 = ConversationStore(db=db)
        turns = store2.get_recent_turns()
        assert len(turns) == 3
        assert turns[0].user_input == "q0"

    def test_limit_from_db(self, db: sqlite3.Connection) -> None:
        store = ConversationStore(db=db)
        for i in range(5):
            store.save_turn(ConversationTurn(user_input=f"q{i}"))
        store2 = ConversationStore(db=db)
        assert len(store2.get_recent_turns(limit=2)) == 2

    def test_has_evidence_flag(self, db: sqlite3.Connection) -> None:
        store = ConversationStore(db=db)
        store.save_turn(ConversationTurn(user_input="q", has_evidence=True))
        store.save_turn(ConversationTurn(user_input="q2", has_evidence=False))
        turns = ConversationStore(db=db).get_recent_turns()
        assert turns[0].has_evidence is True
        assert turns[1].has_evidence is False
