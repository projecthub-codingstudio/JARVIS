"""Tests for Tier 3 user knowledge extraction and storage."""
from __future__ import annotations

import sqlite3

import pytest

from jarvis.app.bootstrap import init_database
from jarvis.app.config import JarvisConfig
from jarvis.memory.user_knowledge import (
    UserKnowledge,
    UserKnowledgeStore,
    extract_knowledge,
)


@pytest.fixture
def db(tmp_path):
    config = JarvisConfig(data_dir=tmp_path / ".jarvis")
    return init_database(config)


class TestExtractKnowledge:
    def test_extracts_korean_role(self) -> None:
        entries = extract_knowledge("나는 Python 개발자입니다", "", turn_id="t1")
        assert len(entries) >= 1
        assert any(e.category == "role" for e in entries)
        assert any("Python 개발자" in e.value for e in entries)

    def test_extracts_english_role(self) -> None:
        entries = extract_knowledge("I'm a data scientist", "", turn_id="t1")
        assert len(entries) >= 1
        assert any("data scientist" in e.value for e in entries)

    def test_extracts_system_info(self) -> None:
        entries = extract_knowledge("MacBook Pro M1 Max로 작업 중입니다", "", turn_id="t1")
        assert len(entries) >= 1
        assert any(e.category == "system" for e in entries)

    def test_no_extraction_from_plain_question(self) -> None:
        entries = extract_knowledge("오늘 날씨 어때?", "", turn_id="t1")
        assert entries == []

    def test_only_extracts_from_user_input(self) -> None:
        """Should NOT extract knowledge from assistant output."""
        entries = extract_knowledge(
            "",  # empty user input
            "당신은 Python 개발자입니다",  # assistant says this
            turn_id="t1",
        )
        assert entries == []


class TestUserKnowledgeStore:
    def test_upsert_and_retrieve(self, db) -> None:
        store = UserKnowledgeStore(db=db)
        store.upsert(UserKnowledge(
            category="role", key="직업/역할", value="개발자", confidence=0.8,
        ))
        entries = store.get_all()
        assert len(entries) == 1
        assert entries[0].value == "개발자"

    def test_upsert_updates_existing(self, db) -> None:
        store = UserKnowledgeStore(db=db)
        store.upsert(UserKnowledge(category="role", key="직업/역할", value="학생"))
        store.upsert(UserKnowledge(category="role", key="직업/역할", value="개발자"))
        entries = store.get_by_category("role")
        assert len(entries) == 1
        assert entries[0].value == "개발자"

    def test_format_for_prompt(self, db) -> None:
        store = UserKnowledgeStore(db=db)
        store.upsert(UserKnowledge(category="role", key="역할", value="개발자", confidence=0.8))
        store.upsert(UserKnowledge(category="system", key="장비", value="M1 Max", confidence=0.7))
        prompt_ctx = store.format_for_prompt()
        assert "[사용자 정보]" in prompt_ctx
        assert "개발자" in prompt_ctx
        assert "M1 Max" in prompt_ctx

    def test_empty_store_returns_empty_prompt(self, db) -> None:
        store = UserKnowledgeStore(db=db)
        assert store.format_for_prompt() == ""

    def test_works_without_db(self) -> None:
        store = UserKnowledgeStore(db=None)
        store.upsert(UserKnowledge(category="test", key="k", value="v"))
        assert len(store.get_all()) == 1
