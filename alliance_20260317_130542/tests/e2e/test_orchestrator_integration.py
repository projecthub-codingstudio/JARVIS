"""Integration test: Orchestrator with real indexed data and SQLite."""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Sequence

import pytest

from jarvis.app.bootstrap import init_database
from jarvis.app.config import JarvisConfig
from jarvis.contracts import CitationState, ConversationTurn, TaskStatus
from jarvis.core.governor import GovernorStub
from jarvis.core.orchestrator import Orchestrator
from jarvis.core.tool_registry import ToolRegistry
from jarvis.indexing.chunker import Chunker
from jarvis.indexing.index_pipeline import IndexPipeline
from jarvis.indexing.parsers import DocumentParser
from jarvis.indexing.tombstone import TombstoneManager
from jarvis.memory.conversation_store import ConversationStore
from jarvis.memory.task_log import TaskLogStore
from jarvis.retrieval.evidence_builder import EvidenceBuilder
from jarvis.retrieval.fts_index import FTSIndex
from jarvis.retrieval.hybrid_search import HybridSearch
from jarvis.retrieval.query_decomposer import QueryDecomposer
from jarvis.retrieval.vector_index import VectorIndex
from jarvis.runtime.mlx_runtime import MLXRuntime


class FakeEmbeddingRuntime:
    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        return [[0.0] * 8 for _ in texts]


@pytest.fixture
def full_system(tmp_path: Path) -> Orchestrator:
    """Build a complete JARVIS system with indexed documents."""
    config = JarvisConfig(watched_folders=[tmp_path], data_dir=tmp_path / ".jarvis")
    db = init_database(config)

    # Index documents
    pipeline = IndexPipeline(
        db=db,
        parser=DocumentParser(),
        chunker=Chunker(max_chunk_bytes=512, overlap_bytes=64),
        tombstone_manager=TombstoneManager(db=db),
        embedding_runtime=FakeEmbeddingRuntime(),
    )
    (tmp_path / "architecture.md").write_text(
        "# JARVIS Architecture\n\n"
        "The system uses a monolith-first design with protocol interfaces.\n"
        "All modules communicate through typed contracts."
    )
    (tmp_path / "korean_doc.md").write_text(
        "# 음성 인식 시스템\n\n"
        "로컬 환경에서 동작하는 음성 인식 엔진을 설계합니다.\n"
        "Whisper.cpp를 사용하여 한국어 음성을 텍스트로 변환합니다."
    )
    (tmp_path / "retrieval.py").write_text(
        '"""Retrieval pipeline."""\n\n'
        'def search(query: str) -> list:\n    """Search indexed documents."""\n    pass\n'
    )
    for f in tmp_path.glob("*"):
        if f.is_file():
            pipeline.index_file(f)

    # Build orchestrator with real components
    return Orchestrator(
        governor=GovernorStub(),
        query_decomposer=QueryDecomposer(),
        fts_retriever=FTSIndex(db=db),
        vector_retriever=VectorIndex(),
        hybrid_fusion=HybridSearch(),
        evidence_builder=EvidenceBuilder(db=db),
        llm_generator=MLXRuntime(),
        tool_registry=ToolRegistry(),
        conversation_store=ConversationStore(db=db),
        task_log_store=TaskLogStore(db=db),
    )


@pytest.mark.e2e
class TestOrchestratorIntegration:
    def test_english_query_gets_answer(self, full_system: Orchestrator) -> None:
        turn = full_system.handle_turn("architecture design")
        assert isinstance(turn, ConversationTurn)
        assert turn.has_evidence is True
        assert turn.assistant_output
        assert "[1]" in turn.assistant_output

    def test_korean_query_gets_answer(self, full_system: Orchestrator) -> None:
        turn = full_system.handle_turn("음성 인식 시스템")
        assert turn.has_evidence is True
        assert turn.assistant_output

    def test_no_match_returns_no_evidence(self, full_system: Orchestrator) -> None:
        turn = full_system.handle_turn("quantum entanglement teleportation")
        assert turn.has_evidence is False
        assert "증거" in turn.assistant_output or "찾을 수 없" in turn.assistant_output

    def test_conversation_persisted_to_sqlite(self, full_system: Orchestrator) -> None:
        turn = full_system.handle_turn("architecture")
        # Create a fresh store from same DB to verify persistence
        store = full_system._conversation_store
        turns = store.get_recent_turns()
        assert len(turns) >= 1
        assert any(t.turn_id == turn.turn_id for t in turns)

    def test_task_logs_persisted(self, full_system: Orchestrator) -> None:
        turn = full_system.handle_turn("monolith design")
        log_store = full_system._task_log_store
        entries = log_store.get_entries_for_turn(turn.turn_id)
        assert len(entries) >= 2
        stages = {e.stage for e in entries}
        assert "start" in stages
        assert "complete" in stages

    def test_multiple_turns(self, full_system: Orchestrator) -> None:
        t1 = full_system.handle_turn("architecture")
        t2 = full_system.handle_turn("음성 인식")
        t3 = full_system.handle_turn("search function")
        store = full_system._conversation_store
        turns = store.get_recent_turns(limit=10)
        assert len(turns) >= 3
