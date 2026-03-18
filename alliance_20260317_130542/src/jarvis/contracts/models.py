"""Core data models for the JARVIS system.

All cross-module communication uses these typed contracts.
No implicit dictionaries cross module boundaries.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from typing import Literal

from jarvis.contracts.states import (
    AccessStatus,
    CitationState,
    IndexingStatus,
    RuntimeTier,
    TaskStatus,
    ThermalState,
)


def _now() -> datetime:
    return datetime.now()


def _uuid() -> str:
    return str(uuid.uuid4())


# --- Retrieval Models ---


@dataclass(frozen=True)
class TypedQueryFragment:
    """A single decomposed query fragment with language/type annotation.

    Produced by QueryDecomposer, consumed by FTS and vector search.
    """

    text: str
    language: str  # "ko", "en", "code"
    query_type: str  # "keyword", "semantic", "hybrid"
    weight: float = 1.0


@dataclass(frozen=True)
class SearchHit:
    """A single FTS search result."""

    chunk_id: str
    document_id: str
    score: float
    snippet: str
    byte_range: tuple[int, int] | None = None
    line_range: tuple[int, int] | None = None


@dataclass(frozen=True)
class VectorHit:
    """A single vector similarity search result."""

    chunk_id: str
    document_id: str
    score: float
    embedding_distance: float


@dataclass(frozen=True)
class HybridSearchResult:
    """Fused search result from RRF over FTS + vector results."""

    chunk_id: str
    document_id: str
    rrf_score: float
    fts_rank: int | None = None
    vector_rank: int | None = None
    snippet: str = ""


# --- Evidence Models ---


@dataclass(frozen=True)
class CitationRecord:
    """A citation linking an evidence item to its source."""

    citation_id: str = field(default_factory=_uuid)
    document_id: str = ""
    chunk_id: str = ""
    label: str = ""
    state: CitationState = CitationState.VALID
    last_verified: datetime = field(default_factory=_now)


@dataclass(frozen=True)
class EvidenceItem:
    """A single piece of verified evidence with its citation."""

    chunk_id: str
    document_id: str
    text: str
    citation: CitationRecord
    relevance_score: float = 0.0
    source_path: str = ""
    heading_path: str = ""


@dataclass(frozen=True)
class VerifiedEvidenceSet:
    """A complete evidence set required before any factual answer (invariant #1).

    May only be produced by EvidenceBuilder when citation metadata
    is complete enough for grounded output.
    """

    items: tuple[EvidenceItem, ...]
    query_fragments: tuple[TypedQueryFragment, ...]
    created_at: datetime = field(default_factory=_now)

    @property
    def is_empty(self) -> bool:
        return len(self.items) == 0

    @property
    def has_warnings(self) -> bool:
        return any(item.citation.state.needs_warning for item in self.items)

    @property
    def warning_citations(self) -> list[CitationRecord]:
        return [item.citation for item in self.items if item.citation.state.needs_warning]


# --- Answer / Draft Models ---


@dataclass(frozen=True)
class AnswerDraft:
    """A generated answer grounded in evidence with citations."""

    content: str
    evidence: VerifiedEvidenceSet
    model_id: str = ""
    generation_time_ms: float = 0.0


@dataclass(frozen=True)
class DraftExportRequest:
    """A request to export a draft artifact. Requires approval."""

    draft: AnswerDraft
    destination: Path
    requested_at: datetime = field(default_factory=_now)


@dataclass(frozen=True)
class DraftExportResult:
    """Result of a draft export attempt."""

    success: bool
    destination: Path | None = None
    approved: bool = False
    error_message: str = ""
    exported_at: datetime | None = None


# --- Memory Models ---


@dataclass
class ConversationTurn:
    """A single conversation turn stored in memory."""

    turn_id: str = field(default_factory=_uuid)
    user_input: str = ""
    assistant_output: str = ""
    has_evidence: bool = False
    created_at: datetime = field(default_factory=_now)
    completed_at: datetime | None = None


@dataclass
class TaskLogEntry:
    """A task log entry for observability and auditing."""

    entry_id: str = field(default_factory=_uuid)
    turn_id: str = ""
    stage: str = ""
    status: TaskStatus = TaskStatus.PENDING
    error_code: str = ""
    duration_ms: float = 0.0
    metadata: dict[str, object] = field(default_factory=dict)
    created_at: datetime = field(default_factory=_now)


# --- Indexing Record Models ---


@dataclass
class DocumentRecord:
    """Metadata for an indexed document."""

    document_id: str = field(default_factory=_uuid)
    path: str = ""
    content_hash: str = ""
    size_bytes: int = 0
    modified_at: datetime = field(default_factory=_now)
    indexing_status: IndexingStatus = IndexingStatus.PENDING
    access_status: AccessStatus = AccessStatus.ACCESSIBLE


@dataclass
class ChunkRecord:
    """A chunk of a document for indexing and retrieval.

    Per Spec Task 1.1: includes lexical_morphs (Korean morpheme-expanded tokens)
    and heading_path for heading-aware document chunking.
    """

    chunk_id: str = field(default_factory=_uuid)
    document_id: str = ""
    byte_start: int = 0
    byte_end: int = 0
    line_start: int = 0
    line_end: int = 0
    text: str = ""
    chunk_hash: str = ""
    lexical_morphs: str = ""
    heading_path: str = ""
    embedding_ref: str | None = None


# --- Runtime Models (Spec Section 3.2) ---


@dataclass(frozen=True)
class RuntimeDecision:
    """Governor's runtime selection decision."""

    tier: RuntimeTier = "balanced"
    backend: Literal["mlx", "llamacpp"] = "mlx"
    model_id: str = ""
    context_window: int = 8192
    reasoning_enabled: bool = False


@dataclass(frozen=True)
class SystemStateSnapshot:
    """Point-in-time system resource snapshot."""

    timestamp: datetime = field(default_factory=_now)
    memory_pressure_pct: float = 0.0
    swap_used_mb: int = 0
    cpu_pct: float = 0.0
    gpu_pct: float = 0.0
    thermal_state: ThermalState = "nominal"
    on_ac_power: bool = True
    battery_pct: int = 100
    indexing_queue_depth: int = 0
