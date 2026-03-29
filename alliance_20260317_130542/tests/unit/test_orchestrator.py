"""Tests for Orchestrator."""
from __future__ import annotations

import sqlite3
from typing import Sequence

import pytest

from jarvis.contracts import (
    AnswerDraft,
    CitationRecord,
    CitationState,
    ConversationTurn,
    EvidenceItem,
    GovernorMode,
    TaskLogEntry,
    TaskStatus,
    VerifiedEvidenceSet,
)
from jarvis.core.governor import GovernorStub
from jarvis.core.orchestrator import Orchestrator
from jarvis.core.tool_registry import ToolRegistry
from jarvis.memory.conversation_store import ConversationStore
from jarvis.memory.task_log import TaskLogStore
from jarvis.retrieval.hybrid_search import HybridSearch
from jarvis.retrieval.query_decomposer import QueryDecomposer
from jarvis.retrieval.vector_index import VectorIndex
from jarvis.runtime.mlx_runtime import MLXRuntime


class StaticEvidenceBuilder:
    def build(self, results: Sequence[object], fragments: Sequence[object]) -> VerifiedEvidenceSet:
        item = EvidenceItem(
            chunk_id="chunk-1",
            document_id="doc-1",
            text="JARVIS architecture evidence",
            citation=CitationRecord(
                document_id="doc-1",
                chunk_id="chunk-1",
                label="[1]",
                state=CitationState.VALID,
            ),
            relevance_score=1.0,
            source_path="/tmp/doc.md",
        )
        return VerifiedEvidenceSet(items=(item,), query_fragments=tuple(fragments))


class EmptyEvidenceBuilder:
    def build(self, results: Sequence[object], fragments: Sequence[object]) -> VerifiedEvidenceSet:
        return VerifiedEvidenceSet(items=(), query_fragments=tuple(fragments))


class StaticFTSRetriever:
    def search(self, fragments: Sequence[object], top_k: int = 10) -> list[object]:
        return []


class DbBackedFTSRetriever(StaticFTSRetriever):
    def __init__(self, db: sqlite3.Connection) -> None:
        self._db = db


class CapturingEvidenceBuilder:
    def __init__(self) -> None:
        self.last_results: list[object] = []

    def build(self, results: Sequence[object], fragments: Sequence[object]) -> VerifiedEvidenceSet:
        self.last_results = list(results)
        item = EvidenceItem(
            chunk_id="chunk-1",
            document_id="doc-1",
            text="captured evidence",
            citation=CitationRecord(
                document_id="doc-1",
                chunk_id="chunk-1",
                label="[1]",
                state=CitationState.VALID,
            ),
            relevance_score=1.0,
            source_path="/tmp/doc.md",
        )
        return VerifiedEvidenceSet(items=(item,), query_fragments=tuple(fragments))


@pytest.fixture
def orchestrator() -> Orchestrator:
    """Orchestrator with explicit positive-path evidence dependencies."""
    return Orchestrator(
        governor=GovernorStub(),
        query_decomposer=QueryDecomposer(),
        fts_retriever=StaticFTSRetriever(),
        vector_retriever=VectorIndex(),
        hybrid_fusion=HybridSearch(),
        evidence_builder=StaticEvidenceBuilder(),
        llm_generator=MLXRuntime(),
        tool_registry=ToolRegistry(),
        conversation_store=ConversationStore(),
        task_log_store=TaskLogStore(),
    )


class TestOrchestratorHandleTurn:
    def test_returns_conversation_turn(self, orchestrator: Orchestrator) -> None:
        turn = orchestrator.handle_turn("프로젝트 구조 설명해줘")
        assert isinstance(turn, ConversationTurn)
        assert turn.user_input == "프로젝트 구조 설명해줘"
        assert turn.assistant_output  # non-empty

    def test_has_evidence_when_results_found(self, orchestrator: Orchestrator) -> None:
        turn = orchestrator.handle_turn("검색 테스트")
        assert turn.has_evidence is True

    def test_answer_contains_citations(self, orchestrator: Orchestrator) -> None:
        turn = orchestrator.handle_turn("아키텍처 설명")
        assert "[1]" in turn.assistant_output

    def test_saves_conversation(self, orchestrator: Orchestrator) -> None:
        turn = orchestrator.handle_turn("대화 저장 테스트")
        store = orchestrator._conversation_store
        turns = store.get_recent_turns()
        assert len(turns) == 1
        assert turns[0].turn_id == turn.turn_id

    def test_logs_task_entries(self, orchestrator: Orchestrator) -> None:
        turn = orchestrator.handle_turn("로그 테스트")
        log_store = orchestrator._task_log_store
        entries = log_store.get_entries_for_turn(turn.turn_id)
        assert len(entries) >= 2  # start + complete
        stages = {e.stage for e in entries}
        assert "start" in stages
        assert "complete" in stages


class TestOrchestratorGovernor:
    def test_governor_denied_returns_error(self) -> None:
        class DeniedGovernor:
            @property
            def mode(self) -> GovernorMode:
                return GovernorMode.SHUTDOWN
            def check_resource_budget(self) -> bool:
                return False
            def should_degrade(self) -> bool:
                return True
            def report_memory_pressure(self) -> float:
                return 0.95

        orch = Orchestrator(
            governor=DeniedGovernor(),
            query_decomposer=QueryDecomposer(),
            fts_retriever=StaticFTSRetriever(),
            vector_retriever=VectorIndex(),
            hybrid_fusion=HybridSearch(),
            evidence_builder=StaticEvidenceBuilder(),
            llm_generator=MLXRuntime(),
            tool_registry=ToolRegistry(),
            conversation_store=ConversationStore(),
            task_log_store=TaskLogStore(),
        )
        turn = orch.handle_turn("test")
        assert turn.has_evidence is False
        assert "리소스" in turn.assistant_output or "부족" in turn.assistant_output


class TestOrchestratorEmptyEvidence:
    def test_empty_query_no_evidence(self) -> None:
        """Empty query → no fragments → empty evidence → no-evidence response."""
        orch = Orchestrator(
            governor=GovernorStub(),
            query_decomposer=QueryDecomposer(),
            fts_retriever=StaticFTSRetriever(),
            vector_retriever=VectorIndex(),
            hybrid_fusion=HybridSearch(),
            evidence_builder=EmptyEvidenceBuilder(),
            llm_generator=MLXRuntime(),
            tool_registry=ToolRegistry(),
            conversation_store=ConversationStore(),
            task_log_store=TaskLogStore(),
        )
        turn = orch.handle_turn("")
        assert turn.has_evidence is False


class TestOrchestratorSafety:
    def test_hard_kill_blocks_destructive_request(self) -> None:
        orch = Orchestrator(
            governor=GovernorStub(),
            query_decomposer=QueryDecomposer(),
            fts_retriever=StaticFTSRetriever(),
            vector_retriever=VectorIndex(),
            hybrid_fusion=HybridSearch(),
            evidence_builder=StaticEvidenceBuilder(),
            llm_generator=MLXRuntime(),
            tool_registry=ToolRegistry(),
            conversation_store=ConversationStore(),
            task_log_store=TaskLogStore(),
        )

        turn = orch.handle_turn("knowledge_base 폴더를 모두 삭제해 줘")

        assert turn.has_evidence is False
        assert "안전 정책" in turn.assistant_output or "파괴적" in turn.assistant_output


class TestOrchestratorTargetedSearch:
    def test_targeted_file_search_boosts_class_signature_hits(self) -> None:
        db = sqlite3.connect(":memory:")
        db.execute(
            "CREATE TABLE documents (document_id TEXT PRIMARY KEY, path TEXT, indexing_status TEXT)"
        )
        db.execute(
            "CREATE TABLE chunks (chunk_id TEXT PRIMARY KEY, document_id TEXT, text TEXT)"
        )
        db.execute(
            "INSERT INTO documents (document_id, path, indexing_status) VALUES (?, ?, ?)",
            ("doc-code", "/tmp/pipeline.py", "INDEXED"),
        )
        db.execute(
            "INSERT INTO documents (document_id, path, indexing_status) VALUES (?, ?, ?)",
            ("doc-pdf", "/tmp/csharp.pdf", "INDEXED"),
        )
        db.execute(
            "INSERT INTO chunks (chunk_id, document_id, text) VALUES (?, ?, ?)",
            ("chunk-code", "doc-code", "class Pipeline:\n    def run(self):\n        pass\n"),
        )
        db.execute(
            "INSERT INTO chunks (chunk_id, document_id, text) VALUES (?, ?, ?)",
            ("chunk-pdf", "doc-pdf", "Pipeline 클래스는 전체 처리 흐름을 설명하는 문서입니다."),
        )
        db.commit()

        orch = Orchestrator(
            governor=GovernorStub(),
            query_decomposer=QueryDecomposer(),
            fts_retriever=DbBackedFTSRetriever(db),
            vector_retriever=VectorIndex(),
            hybrid_fusion=HybridSearch(),
            evidence_builder=StaticEvidenceBuilder(),
            llm_generator=MLXRuntime(),
            tool_registry=ToolRegistry(),
            conversation_store=ConversationStore(),
            task_log_store=TaskLogStore(),
        )

        fragments = QueryDecomposer().decompose("PIPELINE.py 소스에서 PIPELINE CLASS에 대해 설명해 줘")
        hits = orch._targeted_file_search("PIPELINE.py 소스에서 PIPELINE CLASS에 대해 설명해 줘", fragments)

        assert hits
        assert hits[0].document_id == "doc-code"
        assert hits[0].chunk_id == "chunk-code"

    def test_explicit_file_scoped_query_filters_non_target_documents(self) -> None:
        db = sqlite3.connect(":memory:")
        db.execute(
            "CREATE TABLE documents (document_id TEXT PRIMARY KEY, path TEXT, indexing_status TEXT)"
        )
        db.execute(
            "CREATE TABLE chunks (chunk_id TEXT PRIMARY KEY, document_id TEXT, text TEXT)"
        )
        db.execute(
            "INSERT INTO documents (document_id, path, indexing_status) VALUES (?, ?, ?)",
            ("doc-code", "/tmp/pipeline.py", "INDEXED"),
        )
        db.execute(
            "INSERT INTO documents (document_id, path, indexing_status) VALUES (?, ?, ?)",
            ("doc-pdf", "/tmp/csharp.pdf", "INDEXED"),
        )
        db.execute(
            "INSERT INTO chunks (chunk_id, document_id, text) VALUES (?, ?, ?)",
            ("chunk-code", "doc-code", "class Pipeline:\n    def run(self):\n        pass\n"),
        )
        db.execute(
            "INSERT INTO chunks (chunk_id, document_id, text) VALUES (?, ?, ?)",
            ("chunk-pdf", "doc-pdf", "Pipeline 클래스 설명 문서"),
        )
        db.commit()

        class StaticVectorRetriever:
            def search(self, fragments: Sequence[object], top_k: int = 10) -> list[object]:
                from jarvis.contracts import SearchHit
                return [SearchHit(
                    chunk_id="chunk-pdf",
                    document_id="doc-pdf",
                    score=9.0,
                    snippet="Pipeline 클래스 설명 문서",
                )]

        evidence_builder = CapturingEvidenceBuilder()
        orch = Orchestrator(
            governor=GovernorStub(),
            query_decomposer=QueryDecomposer(),
            fts_retriever=DbBackedFTSRetriever(db),
            vector_retriever=StaticVectorRetriever(),
            hybrid_fusion=HybridSearch(),
            evidence_builder=evidence_builder,
            llm_generator=MLXRuntime(),
            tool_registry=ToolRegistry(),
            conversation_store=ConversationStore(),
            task_log_store=TaskLogStore(),
        )

        orch.handle_turn("pipeline.py 소스에서 pipeline 클래스 설명해 줘")

        document_ids = [getattr(item, "document_id", "") for item in evidence_builder.last_results]
        assert document_ids
        assert set(document_ids) == {"doc-code"}
