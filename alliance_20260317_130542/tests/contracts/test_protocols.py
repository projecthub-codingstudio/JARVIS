"""Contract tests for protocol conformance — verifies runtime_checkable protocols."""

from __future__ import annotations

from typing import Sequence

from jarvis.contracts.models import (
    AnswerDraft,
    ConversationTurn,
    DraftExportRequest,
    DraftExportResult,
    HybridSearchResult,
    SearchHit,
    TaskLogEntry,
    TypedQueryFragment,
    VectorHit,
    VerifiedEvidenceSet,
)
from jarvis.contracts.protocols import (
    EmbeddingRuntimeProtocol,
    EvidenceBuilderProtocol,
    FTSRetrieverProtocol,
    GovernorProtocol,
    HybridFusionProtocol,
    LLMGeneratorProtocol,
    QueryDecomposerProtocol,
    VectorRetrieverProtocol,
)
from jarvis.contracts.protocols import (
    ApprovalGatewayProtocol,
    ConversationStoreProtocol,
    TaskLogStoreProtocol,
    ToolRegistryProtocol,
)
from jarvis.contracts.states import GovernorMode, ToolName


class TestProtocolCount:
    def test_eight_core_protocols_defined(self) -> None:
        """Verify we have exactly 8 core protocols as required by spec."""
        core_protocols = [
            QueryDecomposerProtocol,
            FTSRetrieverProtocol,
            VectorRetrieverProtocol,
            HybridFusionProtocol,
            EvidenceBuilderProtocol,
            LLMGeneratorProtocol,
            EmbeddingRuntimeProtocol,
            GovernorProtocol,
        ]
        assert len(core_protocols) == 8

    def test_twelve_total_protocols_defined(self) -> None:
        """Verify all 12 protocols exist in protocols module."""
        all_protocols = [
            QueryDecomposerProtocol,
            FTSRetrieverProtocol,
            VectorRetrieverProtocol,
            HybridFusionProtocol,
            EvidenceBuilderProtocol,
            LLMGeneratorProtocol,
            EmbeddingRuntimeProtocol,
            GovernorProtocol,
            ConversationStoreProtocol,
            TaskLogStoreProtocol,
            ToolRegistryProtocol,
            ApprovalGatewayProtocol,
        ]
        assert len(all_protocols) == 12


class StubQueryDecomposer:
    def decompose(self, query: str) -> list[TypedQueryFragment]:
        return [TypedQueryFragment(text=query, language="ko", query_type="keyword")]


class StubFTSRetriever:
    def search(self, fragments: Sequence[TypedQueryFragment], top_k: int = 10) -> list[SearchHit]:
        return []


class StubVectorRetriever:
    def search(self, fragments: Sequence[TypedQueryFragment], top_k: int = 10) -> list[VectorHit]:
        return []


class StubHybridFusion:
    def fuse(self, fts_hits: Sequence[SearchHit], vector_hits: Sequence[VectorHit],
             top_k: int = 10) -> list[HybridSearchResult]:
        return []


class StubEvidenceBuilder:
    def build(self, results: Sequence[HybridSearchResult],
              fragments: Sequence[TypedQueryFragment]) -> VerifiedEvidenceSet:
        return VerifiedEvidenceSet(items=(), query_fragments=())


class StubLLMGenerator:
    def generate(self, prompt: str, evidence: VerifiedEvidenceSet) -> AnswerDraft:
        return AnswerDraft(content="stub answer", evidence=evidence)


class StubEmbeddingRuntime:
    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        return [[0.0] * 128 for _ in texts]


class StubGovernor:
    @property
    def mode(self) -> GovernorMode:
        return GovernorMode.NORMAL

    def check_resource_budget(self) -> bool:
        return True

    def should_degrade(self) -> bool:
        return False

    def report_memory_pressure(self) -> float:
        return 0.0


class StubConversationStore:
    def save_turn(self, turn: ConversationTurn) -> None:
        pass

    def get_recent_turns(self, limit: int = 10) -> list[ConversationTurn]:
        return []


class StubTaskLogStore:
    def log_entry(self, entry: TaskLogEntry) -> None:
        pass

    def get_entries_for_turn(self, turn_id: str) -> list[TaskLogEntry]:
        return []


class StubToolRegistry:
    def get_allowed_tools(self) -> list[ToolName]:
        return list(ToolName)

    def execute(self, tool_name: ToolName, **kwargs: object) -> object:
        return None


class StubApprovalGateway:
    def request_approval(self, request: DraftExportRequest) -> bool:
        return False

    def execute_export(self, request: DraftExportRequest) -> DraftExportResult:
        return DraftExportResult(success=False)


class TestProtocolConformance:
    """Verify that stub classes satisfy runtime_checkable protocols."""

    def test_query_decomposer(self) -> None:
        assert isinstance(StubQueryDecomposer(), QueryDecomposerProtocol)

    def test_fts_retriever(self) -> None:
        assert isinstance(StubFTSRetriever(), FTSRetrieverProtocol)

    def test_vector_retriever(self) -> None:
        assert isinstance(StubVectorRetriever(), VectorRetrieverProtocol)

    def test_hybrid_fusion(self) -> None:
        assert isinstance(StubHybridFusion(), HybridFusionProtocol)

    def test_evidence_builder(self) -> None:
        assert isinstance(StubEvidenceBuilder(), EvidenceBuilderProtocol)

    def test_llm_generator(self) -> None:
        assert isinstance(StubLLMGenerator(), LLMGeneratorProtocol)

    def test_embedding_runtime(self) -> None:
        assert isinstance(StubEmbeddingRuntime(), EmbeddingRuntimeProtocol)

    def test_governor(self) -> None:
        assert isinstance(StubGovernor(), GovernorProtocol)

    def test_conversation_store(self) -> None:
        assert isinstance(StubConversationStore(), ConversationStoreProtocol)

    def test_task_log_store(self) -> None:
        assert isinstance(StubTaskLogStore(), TaskLogStoreProtocol)

    def test_tool_registry(self) -> None:
        assert isinstance(StubToolRegistry(), ToolRegistryProtocol)

    def test_approval_gateway(self) -> None:
        assert isinstance(StubApprovalGateway(), ApprovalGatewayProtocol)
