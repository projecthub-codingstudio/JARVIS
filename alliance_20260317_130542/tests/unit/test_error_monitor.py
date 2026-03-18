"""Tests for error thresholds and safe mode behavior."""
from __future__ import annotations

from datetime import datetime, timedelta

from jarvis.contracts import (
    AnswerDraft,
    ConversationTurn,
    HybridSearchResult,
    TaskLogEntry,
    ToolName,
    TypedQueryFragment,
    VerifiedEvidenceSet,
)
from jarvis.core.error_monitor import ErrorMonitor
from jarvis.core.governor import GovernorStub
from jarvis.core.orchestrator import Orchestrator
from jarvis.core.tool_registry import ToolRegistry
from jarvis.memory.conversation_store import ConversationStore
from jarvis.memory.task_log import TaskLogStore
from jarvis.retrieval.evidence_builder import EvidenceBuilder
from jarvis.retrieval.hybrid_search import HybridSearch


class TestErrorMonitor:
    def test_blocks_tools_after_five_same_errors_in_five_minutes(self) -> None:
        monitor = ErrorMonitor()
        now = datetime.now()
        for i in range(5):
            monitor.record_error(
                "TOOL_EXECUTION_FAILED",
                category="tool",
                occurred_at=now + timedelta(seconds=i),
            )
        assert monitor.should_block_tools(occurred_at=now + timedelta(minutes=4))

    def test_safe_mode_when_model_and_index_fail_within_ten_minutes(self) -> None:
        monitor = ErrorMonitor()
        now = datetime.now()
        monitor.record_error("MODEL_LOAD_FAILED", category="model", occurred_at=now)
        monitor.record_error("INDEX_WRITE_FAILED", category="index", occurred_at=now + timedelta(minutes=3))
        assert monitor.safe_mode_active(occurred_at=now + timedelta(minutes=5))

    def test_safe_mode_expires_after_window(self) -> None:
        monitor = ErrorMonitor()
        now = datetime.now()
        monitor.record_error("MODEL_LOAD_FAILED", category="model", occurred_at=now)
        monitor.record_error("INDEX_WRITE_FAILED", category="index", occurred_at=now + timedelta(minutes=1))
        assert monitor.safe_mode_active(occurred_at=now + timedelta(minutes=2))
        assert not monitor.safe_mode_active(occurred_at=now + timedelta(minutes=12))

    def test_two_model_failures_enable_degraded_mode(self) -> None:
        monitor = ErrorMonitor()
        now = datetime.now()
        monitor.record_error("MODEL_LOAD_FAILED", category="model", occurred_at=now)
        monitor.record_error("MODEL_LOAD_FAILED", category="model", occurred_at=now + timedelta(seconds=10))
        assert monitor.degraded_mode is True
        assert monitor.generation_blocked is False

    def test_three_model_failures_block_generation(self) -> None:
        monitor = ErrorMonitor()
        now = datetime.now()
        for i in range(3):
            monitor.record_error(
                "MODEL_LOAD_FAILED",
                category="model",
                occurred_at=now + timedelta(seconds=i),
            )
        assert monitor.generation_blocked is True

    def test_three_sqlite_locks_block_writes_and_request_rebuild(self) -> None:
        monitor = ErrorMonitor()
        now = datetime.now()
        for i in range(3):
            monitor.record_error(
                "SQLITE_LOCK",
                category="index",
                occurred_at=now + timedelta(seconds=i),
            )
        assert monitor.write_blocked is True
        assert monitor.rebuild_index_required is True

    def test_integrity_failure_enables_read_only_mode(self) -> None:
        monitor = ErrorMonitor()
        monitor.record_error("SQLITE_INTEGRITY", category="index")

        assert monitor.read_only_mode is True
        assert monitor.write_blocked is True
        assert monitor.rebuild_index_required is True


class StubDecomposer:
    def decompose(self, query: str) -> list[TypedQueryFragment]:
        return [TypedQueryFragment(text=query, language="ko", query_type="keyword")]


class StubFTS:
    def search(self, fragments: list[TypedQueryFragment], top_k: int = 10) -> list:
        return []


class StubVector:
    def search(self, fragments: list[TypedQueryFragment], top_k: int = 10) -> list:
        return []


class StubEvidenceBuilder:
    def build(self, results: list[HybridSearchResult], fragments: list[TypedQueryFragment]) -> VerifiedEvidenceSet:
        from jarvis.contracts import CitationRecord, EvidenceItem

        item = EvidenceItem(
            chunk_id="c1",
            document_id="d1",
            text="검색 결과 본문입니다.",
            citation=CitationRecord(document_id="d1", chunk_id="c1", label="[1]"),
            source_path="/tmp/source.md",
            relevance_score=1.0,
        )
        return VerifiedEvidenceSet(items=(item,), query_fragments=tuple(fragments))


class StubGenerator:
    def generate(
        self,
        prompt: str,
        evidence: VerifiedEvidenceSet,
        *,
        recent_turns: list[ConversationTurn] | None = None,
    ) -> AnswerDraft:
        return AnswerDraft(content="생성 응답", evidence=evidence, model_id="stub")


class TestSafeModeOrchestrator:
    def test_safe_mode_returns_search_only_response(self) -> None:
        monitor = ErrorMonitor()
        now = datetime.now()
        monitor.record_error("MODEL_LOAD_FAILED", category="model", occurred_at=now)
        monitor.record_error("INDEX_WRITE_FAILED", category="index", occurred_at=now + timedelta(minutes=1))

        orchestrator = Orchestrator(
            governor=GovernorStub(),
            query_decomposer=StubDecomposer(),
            fts_retriever=StubFTS(),
            vector_retriever=StubVector(),
            hybrid_fusion=HybridSearch(),
            evidence_builder=StubEvidenceBuilder(),
            llm_generator=StubGenerator(),
            tool_registry=ToolRegistry(error_monitor=monitor),
            conversation_store=ConversationStore(),
            task_log_store=TaskLogStore(),
            error_monitor=monitor,
        )

        turn = orchestrator.handle_turn("검색 결과만 보여줘")
        assert "안전 모드" in turn.assistant_output
        assert "생성 기능" in turn.assistant_output

    def test_degraded_mode_does_not_yet_block_generation(self) -> None:
        monitor = ErrorMonitor()
        now = datetime.now()
        monitor.record_error("MODEL_LOAD_FAILED", category="model", occurred_at=now)
        monitor.record_error("MODEL_LOAD_FAILED", category="model", occurred_at=now + timedelta(seconds=1))

        orchestrator = Orchestrator(
            governor=GovernorStub(),
            query_decomposer=StubDecomposer(),
            fts_retriever=StubFTS(),
            vector_retriever=StubVector(),
            hybrid_fusion=HybridSearch(),
            evidence_builder=StubEvidenceBuilder(),
            llm_generator=StubGenerator(),
            tool_registry=ToolRegistry(error_monitor=monitor),
            conversation_store=ConversationStore(),
            task_log_store=TaskLogStore(),
            error_monitor=monitor,
        )

        turn = orchestrator.handle_turn("검색 결과만 보여줘")
        assert monitor.degraded_mode is True
        assert monitor.generation_blocked is False
        assert turn.assistant_output == "생성 응답"

    def test_tool_registry_blocks_when_threshold_crossed(self) -> None:
        monitor = ErrorMonitor()
        now = datetime.now()
        for i in range(5):
            monitor.record_error(
                "TOOL_EXECUTION_FAILED",
                category="tool",
                occurred_at=now + timedelta(seconds=i),
            )

        registry = ToolRegistry(error_monitor=monitor)
        registry.register_handler(ToolName.READ_FILE, lambda **_: "ok")

        from jarvis.contracts import ToolError

        try:
            registry.execute(ToolName.READ_FILE)
            assert False, "expected ToolError"
        except ToolError as exc:
            assert "blocked" in exc.message

    def test_tool_registry_blocks_draft_export_when_writes_blocked(self) -> None:
        monitor = ErrorMonitor()
        now = datetime.now()
        for i in range(3):
            monitor.record_error("SQLITE_LOCK", category="index", occurred_at=now + timedelta(seconds=i))

        registry = ToolRegistry(error_monitor=monitor)
        registry.register_handler(ToolName.DRAFT_EXPORT, lambda **_: "ok")

        from jarvis.contracts import ToolError

        try:
            registry.execute(ToolName.DRAFT_EXPORT)
            assert False, "expected ToolError"
        except ToolError as exc:
            assert "Write operations" in exc.message
