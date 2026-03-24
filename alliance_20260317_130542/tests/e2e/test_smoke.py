"""E2E smoke tests using the shipped wiring with explicit evidence fixtures.

These tests validate the full wiring from query to response while keeping
evidence explicit. This matches the runtime invariant that no factual
answer should be produced from retrieval stubs alone.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from jarvis.app.bootstrap import init_database
from jarvis.app.config import JarvisConfig
from jarvis.cli.approval import CLIApprovalGateway
from jarvis.contracts.models import (
    AnswerDraft,
    CitationRecord,
    EvidenceItem,
    ConversationTurn,
    DraftExportRequest,
    SearchHit,
    TaskLogEntry,
    TypedQueryFragment,
    VectorHit,
    VerifiedEvidenceSet,
)
from jarvis.contracts.protocols import (
    ApprovalGatewayProtocol,
    ConversationStoreProtocol,
    EvidenceBuilderProtocol,
    FTSRetrieverProtocol,
    GovernorProtocol,
    HybridFusionProtocol,
    LLMGeneratorProtocol,
    QueryDecomposerProtocol,
    TaskLogStoreProtocol,
    VectorRetrieverProtocol,
)
from jarvis.contracts.states import CitationState, GovernorMode, TaskStatus, ToolName
from jarvis.core.governor import GovernorStub
from jarvis.memory.conversation_store import ConversationStore
from jarvis.memory.task_log import TaskLogStore
from jarvis.observability.metrics import MetricName, MetricsCollector
from jarvis.retrieval.evidence_builder import EvidenceBuilder
from jarvis.retrieval.fts_index import FTSIndex
from jarvis.retrieval.hybrid_search import HybridSearch
from jarvis.retrieval.query_decomposer import QueryDecomposer
from jarvis.retrieval.vector_index import VectorIndex
from jarvis.runtime.mlx_runtime import MLXRuntime


class StaticFTS:
    def search(
        self,
        fragments: list[TypedQueryFragment],
        top_k: int = 10,
    ) -> list[SearchHit]:
        return [
            SearchHit(
                chunk_id="chunk-1",
                document_id="doc-1",
                score=1.0,
                snippet="JARVIS architecture evidence",
            )
        ]


class EmptyVector:
    def search(
        self,
        fragments: list[TypedQueryFragment],
        top_k: int = 10,
    ) -> list[VectorHit]:
        return []


class StaticEvidenceBuilder:
    def build(self, results, fragments) -> VerifiedEvidenceSet:
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


# ---- Smoke test orchestrator (simplified E2E flow) ----


def run_answer_flow(
    query: str,
    decomposer: QueryDecomposer,
    fts: FTSIndex,
    vector: VectorIndex,
    fusion: HybridSearch,
    evidence_builder: EvidenceBuilder,
    generator: MLXRuntime,
    governor: GovernorStub,
    conversation_store: ConversationStore,
    task_log_store: TaskLogStore,
    metrics: MetricsCollector,
) -> AnswerDraft:
    """Simulate the full answer flow as described in spec section 9.1."""
    # 1. Check governor
    assert governor.check_resource_budget()

    # 2. Create turn
    turn = ConversationTurn(user_input=query)
    task_log_store.log_entry(TaskLogEntry(
        turn_id=turn.turn_id, stage="start", status=TaskStatus.RUNNING,
    ))

    # 3. Decompose query (invariant #2)
    with metrics.measure(MetricName.QUERY_LATENCY_MS):
        fragments = decomposer.decompose(query)
    assert len(fragments) > 0

    # 4. Run FTS search
    with metrics.measure(MetricName.QUERY_LATENCY_MS):
        fts_hits = fts.search(fragments)

    # 5. Run vector search
    with metrics.measure(MetricName.TTFT_MS):
        vector_hits = vector.search(fragments)

    # 6. Fuse results
    with metrics.measure(MetricName.TRUST_RECOVERY_TIME_MS):
        hybrid_results = fusion.fuse(fts_hits, vector_hits)

    # 7. Build evidence (invariant #1 gate)
    with metrics.measure(MetricName.TRUST_RECOVERY_TIME_MS):
        evidence = evidence_builder.build(hybrid_results, fragments)

    # 8. Guard: refuse if no evidence
    if evidence.is_empty:
        metrics.record(MetricName.CITATION_MISSING_RATE, 1.0)
        turn.assistant_output = "No evidence found to answer this query."
        turn.has_evidence = False
        conversation_store.save_turn(turn)
        return AnswerDraft(content=turn.assistant_output, evidence=evidence)

    # 9. Generate answer
    with metrics.measure(MetricName.TTFT_MS):
        answer = generator.generate(query, evidence)

    # 10. Log and return
    turn.assistant_output = answer.content
    turn.has_evidence = True
    conversation_store.save_turn(turn)
    task_log_store.log_entry(TaskLogEntry(
        turn_id=turn.turn_id, stage="complete", status=TaskStatus.COMPLETED,
    ))

    return answer


# ---- Test classes ----


@pytest.fixture
def smoke_deps() -> dict[str, object]:
    return {
        "decomposer": QueryDecomposer(),
        "fts": StaticFTS(),
        "vector": EmptyVector(),
        "fusion": HybridSearch(),
        "evidence_builder": StaticEvidenceBuilder(),
        "generator": MLXRuntime(),
        "governor": GovernorStub(),
        "conversation_store": ConversationStore(),
        "task_log_store": TaskLogStore(),
        "metrics": MetricsCollector(),
    }


@pytest.mark.e2e
class TestSmokeAnswerFlow:
    """Smoke test: full answer flow with explicit verified evidence."""

    def test_korean_query_produces_answer(self, smoke_deps: dict[str, object]) -> None:
        answer = run_answer_flow("프로젝트 아키텍처 설명해줘", **smoke_deps)  # type: ignore[arg-type]
        assert answer.content
        assert not answer.evidence.is_empty
        assert "[1]" in answer.content

    def test_answer_has_citations(self, smoke_deps: dict[str, object]) -> None:
        answer = run_answer_flow("검색 시스템 구조", **smoke_deps)  # type: ignore[arg-type]
        assert len(answer.evidence.items) > 0
        for item in answer.evidence.items:
            assert item.citation.state == CitationState.VALID
            assert item.citation.label

    def test_metrics_recorded(self, smoke_deps: dict[str, object]) -> None:
        run_answer_flow("테스트 쿼리", **smoke_deps)  # type: ignore[arg-type]
        metrics: MetricsCollector = smoke_deps["metrics"]  # type: ignore[assignment]
        assert metrics.get_events(MetricName.QUERY_LATENCY_MS)
        assert metrics.get_events(MetricName.TTFT_MS)

    def test_conversation_turn_saved(self, smoke_deps: dict[str, object]) -> None:
        run_answer_flow("대화 기록 테스트", **smoke_deps)  # type: ignore[arg-type]
        store: ConversationStore = smoke_deps["conversation_store"]  # type: ignore[assignment]
        turns = store.get_recent_turns()
        assert len(turns) == 1
        assert turns[0].user_input == "대화 기록 테스트"
        assert turns[0].has_evidence is True

    def test_task_logs_recorded(self, smoke_deps: dict[str, object]) -> None:
        run_answer_flow("로그 테스트", **smoke_deps)  # type: ignore[arg-type]
        log_store: TaskLogStore = smoke_deps["task_log_store"]  # type: ignore[assignment]
        assert len(log_store._entries) >= 2  # start + complete


@pytest.mark.e2e
class TestSmokeDraftExport:
    """Smoke test: draft export flow."""

    def test_approved_export(self, tmp_path: Path, smoke_deps: dict[str, object]) -> None:
        answer = run_answer_flow("내보내기 테스트", **smoke_deps)  # type: ignore[arg-type]
        gateway = CLIApprovalGateway(auto_approve=True)
        export_dest = tmp_path / "draft.md"
        request = DraftExportRequest(draft=answer, destination=export_dest)

        # Approval gate
        approved = gateway.request_approval(request)
        assert approved

        result = gateway.execute_export(request)
        assert result.success
        assert result.approved


@pytest.mark.e2e
class TestSmokeSchemaBootstrap:
    """Smoke test: database initialization via bootstrap."""

    def test_bootstrap_creates_db(self, tmp_path: Path) -> None:
        config = JarvisConfig(
            watched_folders=[tmp_path],
            data_dir=tmp_path / ".jarvis",
        )
        conn = init_database(config)

        # Verify tables exist
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
        tables = {row[0] for row in cursor.fetchall()}
        assert "documents" in tables
        assert "chunks" in tables
        assert "chunks_fts" in tables
        assert "citations" in tables
        assert "conversation_turns" in tables
        assert "task_logs" in tables
        conn.close()


@pytest.mark.e2e
class TestSmokeProtocolConformance:
    """Smoke test: shipped stub implementations satisfy their protocols."""

    def test_query_decomposer(self) -> None:
        assert isinstance(QueryDecomposer(), QueryDecomposerProtocol)

    def test_fts_retriever(self) -> None:
        assert isinstance(FTSIndex(), FTSRetrieverProtocol)

    def test_vector_retriever(self) -> None:
        assert isinstance(VectorIndex(), VectorRetrieverProtocol)

    def test_hybrid_fusion(self) -> None:
        assert isinstance(HybridSearch(), HybridFusionProtocol)

    def test_evidence_builder(self) -> None:
        assert isinstance(EvidenceBuilder(), EvidenceBuilderProtocol)

    def test_llm_generator(self) -> None:
        assert isinstance(MLXRuntime(), LLMGeneratorProtocol)

    def test_governor(self) -> None:
        assert isinstance(GovernorStub(), GovernorProtocol)

    def test_conversation_store(self) -> None:
        assert isinstance(ConversationStore(), ConversationStoreProtocol)

    def test_task_log_store(self) -> None:
        assert isinstance(TaskLogStore(), TaskLogStoreProtocol)

    def test_approval_gateway(self) -> None:
        assert isinstance(CLIApprovalGateway(), ApprovalGatewayProtocol)


@pytest.mark.e2e
class TestSmokeInvariantEnforcement:
    """Smoke test: architecture invariants are enforced."""

    def test_invariant_1_no_answer_without_evidence(self) -> None:
        """Invariant #1: No factual answer without VerifiedEvidenceSet."""
        empty_evidence = VerifiedEvidenceSet(items=(), query_fragments=())
        assert empty_evidence.is_empty
        generator = MLXRuntime()
        answer = generator.generate("test", empty_evidence)
        assert "증거가 없" in answer.content or "없" in answer.content

    def test_invariant_5_citation_states(self) -> None:
        """Invariant #5: Only 5 citation states allowed."""
        valid_states = {s.value for s in CitationState}
        assert valid_states == {"VALID", "STALE", "REINDEXING", "MISSING", "ACCESS_LOST"}

    def test_invariant_6_only_three_tools(self) -> None:
        """Invariant #6: Phase 1 exposes only 3 tools."""
        assert len(ToolName) == 3
        assert {t.value for t in ToolName} == {"read_file", "search_files", "draft_export"}
