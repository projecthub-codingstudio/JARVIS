"""Protocol interfaces for the JARVIS system.

Core protocols covering retrieval, runtime, governor, memory,
tool registry, and approval boundaries.
These are frozen at Day 0 — interface changes are not permitted.
Stub implementations are allowed; interface redesign is not.
"""

from __future__ import annotations

from typing import Protocol, Sequence, runtime_checkable

from jarvis.contracts.models import (
    AnswerDraft,
    ConversationTurn,
    DraftExportRequest,
    DraftExportResult,
    HybridSearchResult,
    RuntimeDecision,
    SearchHit,
    TaskLogEntry,
    TypedQueryFragment,
    VectorHit,
    VerifiedEvidenceSet,
)
from jarvis.contracts.states import GovernorMode, ToolName


# --- Retrieval Protocols ---


@runtime_checkable
class QueryDecomposerProtocol(Protocol):
    """Decomposes a user query into typed fragments for retrieval."""

    def decompose(self, query: str) -> list[TypedQueryFragment]:
        """Split a mixed Korean/code query into typed fragments."""
        ...


@runtime_checkable
class FTSRetrieverProtocol(Protocol):
    """Full-text search retrieval via SQLite FTS5."""

    def search(self, fragments: Sequence[TypedQueryFragment], top_k: int = 10) -> list[SearchHit]:
        """Search FTS index with decomposed query fragments."""
        ...


@runtime_checkable
class VectorRetrieverProtocol(Protocol):
    """Vector similarity retrieval via embedding index."""

    def search(
        self, fragments: Sequence[TypedQueryFragment], top_k: int = 10
    ) -> list[VectorHit]:
        """Search vector index with decomposed query fragments."""
        ...


@runtime_checkable
class HybridFusionProtocol(Protocol):
    """Fuses FTS and vector results using RRF."""

    def fuse(
        self,
        fts_hits: Sequence[SearchHit],
        vector_hits: Sequence[VectorHit],
        top_k: int = 10,
    ) -> list[HybridSearchResult]:
        """Fuse FTS and vector results with Reciprocal Rank Fusion."""
        ...


@runtime_checkable
class EvidenceBuilderProtocol(Protocol):
    """Builds verified evidence sets from ranked search results."""

    def build(
        self,
        results: Sequence[HybridSearchResult],
        fragments: Sequence[TypedQueryFragment],
    ) -> VerifiedEvidenceSet:
        """Build a VerifiedEvidenceSet from hybrid search results.

        Must reject items that cannot be resolved to a document/chunk source.
        Returns empty VerifiedEvidenceSet if no evidence qualifies.
        """
        ...


# --- Runtime Protocols ---


@runtime_checkable
class LLMGeneratorProtocol(Protocol):
    """Local LLM generation via MLX."""

    def generate(self, prompt: str, evidence: VerifiedEvidenceSet) -> AnswerDraft:
        """Generate a grounded answer from evidence.

        Must not generate if evidence is empty (invariant #1).
        """
        ...


@runtime_checkable
class LLMBackendProtocol(Protocol):
    """LLM backend protocol per Implementation Spec Section 2.2.

    Supports load/unload lifecycle and grounded generation.
    MLX primary, llama.cpp compatibility backend.
    """

    def load(self, decision: RuntimeDecision) -> None:
        """Load the model specified by RuntimeDecision."""
        ...

    def unload(self) -> None:
        """Unload the current model and release memory."""
        ...

    def generate(
        self, prompt: str, context: str, intent: str
    ) -> str:
        """Generate a response given prompt, assembled context, and intent.

        Args:
            prompt: User query text.
            context: Assembled retrieved context string.
            intent: Intent classification (e.g. 'read_only').

        Returns:
            Generated response text.
        """
        ...


@runtime_checkable
class EmbeddingRuntimeProtocol(Protocol):
    """Local embedding generation via MLX."""

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        """Generate embeddings for a batch of texts."""
        ...


# --- Governor Protocol ---


@runtime_checkable
class GovernorProtocol(Protocol):
    """Resource and safety governor. Interface frozen at Day 0 (invariant #4)."""

    @property
    def mode(self) -> GovernorMode:
        """Current governor operational mode."""
        ...

    def check_resource_budget(self) -> bool:
        """Return True if resources are available for the next operation."""
        ...

    def should_degrade(self) -> bool:
        """Return True if the system should enter degraded mode."""
        ...

    def report_memory_pressure(self) -> float:
        """Return memory pressure as a fraction (0.0 to 1.0)."""
        ...


# --- Memory Protocols ---


@runtime_checkable
class ConversationStoreProtocol(Protocol):
    """Persistent conversation history storage."""

    def save_turn(self, turn: ConversationTurn) -> None:
        """Persist a conversation turn."""
        ...

    def get_recent_turns(self, limit: int = 10) -> list[ConversationTurn]:
        """Retrieve recent conversation turns."""
        ...


@runtime_checkable
class TaskLogStoreProtocol(Protocol):
    """Persistent task log storage for observability."""

    def log_entry(self, entry: TaskLogEntry) -> None:
        """Persist a task log entry."""
        ...

    def get_entries_for_turn(self, turn_id: str) -> list[TaskLogEntry]:
        """Retrieve all task log entries for a given turn."""
        ...


# --- Tool Protocol ---


@runtime_checkable
class ToolRegistryProtocol(Protocol):
    """Registry for allowed tools (invariant #6: only 3 tools in Phase 1)."""

    def get_allowed_tools(self) -> list[ToolName]:
        """Return the list of allowed tool names."""
        ...

    def execute(
        self,
        tool_name: ToolName,
        **kwargs: object,
    ) -> object:
        """Execute a registered tool by name."""
        ...


# --- Approval Protocol ---


@runtime_checkable
class ApprovalGatewayProtocol(Protocol):
    """Approval gateway for draft_export (invariant #3)."""

    def request_approval(self, request: DraftExportRequest) -> bool:
        """Present the export request and return True if user approves."""
        ...

    def execute_export(self, request: DraftExportRequest) -> DraftExportResult:
        """Execute the export after approval. Must not be called without approval."""
        ...
