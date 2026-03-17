"""Tests for Orchestrator."""
from __future__ import annotations

from typing import Sequence

import pytest

from jarvis.contracts import (
    AnswerDraft,
    ConversationTurn,
    GovernorMode,
    HybridSearchResult,
    SearchHit,
    TaskLogEntry,
    TaskStatus,
    TypedQueryFragment,
    VectorHit,
    VerifiedEvidenceSet,
)
from jarvis.core.governor import GovernorStub
from jarvis.core.orchestrator import Orchestrator
from jarvis.core.tool_registry import ToolRegistry
from jarvis.memory.conversation_store import ConversationStore
from jarvis.memory.task_log import TaskLogStore
from jarvis.retrieval.evidence_builder import EvidenceBuilder
from jarvis.retrieval.fts_index import FTSIndex
from jarvis.retrieval.hybrid_search import HybridSearch
from jarvis.retrieval.query_decomposer import QueryDecomposer
from jarvis.retrieval.vector_index import VectorIndex
from jarvis.runtime.mlx_runtime import MLXRuntime


@pytest.fixture
def orchestrator() -> Orchestrator:
    """Orchestrator with all stub/in-memory dependencies."""
    return Orchestrator(
        governor=GovernorStub(),
        query_decomposer=QueryDecomposer(),
        fts_retriever=FTSIndex(),
        vector_retriever=VectorIndex(),
        hybrid_fusion=HybridSearch(),
        evidence_builder=EvidenceBuilder(),
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
        # Stubs always return results, so evidence should exist
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
            fts_retriever=FTSIndex(),
            vector_retriever=VectorIndex(),
            hybrid_fusion=HybridSearch(),
            evidence_builder=EvidenceBuilder(),
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
            fts_retriever=FTSIndex(),
            vector_retriever=VectorIndex(),
            hybrid_fusion=HybridSearch(),
            evidence_builder=EvidenceBuilder(),
            llm_generator=MLXRuntime(),
            tool_registry=ToolRegistry(),
            conversation_store=ConversationStore(),
            task_log_store=TaskLogStore(),
        )
        turn = orch.handle_turn("")
        assert turn.has_evidence is False
