"""Contract tests for dataclass models — serialization, validation, invariants."""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

import pytest

from jarvis.contracts.models import (
    AnswerDraft,
    CitationRecord,
    ConversationTurn,
    DraftExportRequest,
    DraftExportResult,
    EvidenceItem,
    HybridSearchResult,
    SearchHit,
    TaskLogEntry,
    TypedQueryFragment,
    VectorHit,
    VerifiedEvidenceSet,
)
from jarvis.contracts.models import ChunkRecord, DocumentRecord
from jarvis.contracts.states import CitationState, IndexingStatus, TaskStatus


class TestTypedQueryFragment:
    def test_creation(self) -> None:
        frag = TypedQueryFragment(text="검색어", language="ko", query_type="keyword")
        assert frag.text == "검색어"
        assert frag.language == "ko"
        assert frag.weight == 1.0

    def test_frozen(self) -> None:
        frag = TypedQueryFragment(text="test", language="en", query_type="semantic")
        with pytest.raises(AttributeError):
            frag.text = "changed"  # type: ignore[misc]

    def test_serialization(self) -> None:
        frag = TypedQueryFragment(text="test", language="en", query_type="hybrid", weight=0.8)
        d = asdict(frag)
        assert d["text"] == "test"
        assert d["weight"] == 0.8
        # Roundtrip through JSON
        json_str = json.dumps(d)
        restored = json.loads(json_str)
        assert restored["text"] == "test"


class TestSearchHit:
    def test_creation_with_ranges(self) -> None:
        hit = SearchHit(
            chunk_id="c1", document_id="d1", score=0.95,
            snippet="found text", byte_range=(0, 100), line_range=(1, 5),
        )
        assert hit.score == 0.95
        assert hit.byte_range == (0, 100)

    def test_optional_ranges(self) -> None:
        hit = SearchHit(chunk_id="c1", document_id="d1", score=0.5, snippet="text")
        assert hit.byte_range is None
        assert hit.line_range is None


class TestVectorHit:
    def test_creation(self) -> None:
        hit = VectorHit(chunk_id="c1", document_id="d1", score=0.88, embedding_distance=0.12)
        assert hit.embedding_distance == 0.12


class TestHybridSearchResult:
    def test_creation(self) -> None:
        result = HybridSearchResult(
            chunk_id="c1", document_id="d1", rrf_score=0.5,
            fts_rank=1, vector_rank=3, snippet="matched",
        )
        assert result.rrf_score == 0.5
        assert result.fts_rank == 1

    def test_optional_ranks(self) -> None:
        result = HybridSearchResult(chunk_id="c1", document_id="d1", rrf_score=0.3)
        assert result.fts_rank is None
        assert result.vector_rank is None


class TestCitationRecord:
    def test_default_state(self) -> None:
        citation = CitationRecord()
        assert citation.state == CitationState.VALID
        assert citation.citation_id  # auto-generated UUID

    def test_custom_state(self) -> None:
        citation = CitationRecord(state=CitationState.STALE)
        assert citation.state == CitationState.STALE


class TestEvidenceItem:
    def test_creation(self) -> None:
        citation = CitationRecord(document_id="d1", chunk_id="c1", label="[1]")
        item = EvidenceItem(
            chunk_id="c1", document_id="d1", text="evidence text",
            citation=citation, relevance_score=0.9,
        )
        assert item.citation.label == "[1]"
        assert item.relevance_score == 0.9


class TestVerifiedEvidenceSet:
    def test_empty_set(self) -> None:
        ves = VerifiedEvidenceSet(items=(), query_fragments=())
        assert ves.is_empty
        assert not ves.has_warnings

    def test_set_with_items(self) -> None:
        citation = CitationRecord(document_id="d1", chunk_id="c1", label="[1]")
        item = EvidenceItem(
            chunk_id="c1", document_id="d1", text="text", citation=citation,
        )
        frag = TypedQueryFragment(text="query", language="ko", query_type="keyword")
        ves = VerifiedEvidenceSet(items=(item,), query_fragments=(frag,))
        assert not ves.is_empty
        assert not ves.has_warnings

    def test_warning_citations(self) -> None:
        stale_citation = CitationRecord(state=CitationState.STALE)
        missing_citation = CitationRecord(state=CitationState.MISSING)
        valid_citation = CitationRecord(state=CitationState.VALID)

        items = (
            EvidenceItem(chunk_id="c1", document_id="d1", text="t1", citation=stale_citation),
            EvidenceItem(chunk_id="c2", document_id="d1", text="t2", citation=valid_citation),
            EvidenceItem(chunk_id="c3", document_id="d1", text="t3", citation=missing_citation),
        )
        ves = VerifiedEvidenceSet(items=items, query_fragments=())
        assert ves.has_warnings
        assert len(ves.warning_citations) == 2


class TestAnswerDraft:
    def test_creation(self) -> None:
        ves = VerifiedEvidenceSet(items=(), query_fragments=())
        draft = AnswerDraft(content="Answer text", evidence=ves, model_id="test-model")
        assert draft.content == "Answer text"
        assert draft.model_id == "test-model"


class TestDraftExportRequest:
    def test_creation(self) -> None:
        ves = VerifiedEvidenceSet(items=(), query_fragments=())
        draft = AnswerDraft(content="content", evidence=ves)
        req = DraftExportRequest(draft=draft, destination=Path("/tmp/test.md"))
        assert req.destination == Path("/tmp/test.md")


class TestDraftExportResult:
    def test_success(self) -> None:
        result = DraftExportResult(
            success=True, destination=Path("/tmp/test.md"),
            approved=True, exported_at=datetime.now(),
        )
        assert result.success
        assert result.approved

    def test_denied(self) -> None:
        result = DraftExportResult(success=False, approved=False, error_message="User denied")
        assert not result.success
        assert result.error_message == "User denied"


class TestConversationTurn:
    def test_creation(self) -> None:
        turn = ConversationTurn(user_input="hello", assistant_output="hi")
        assert turn.turn_id  # auto-generated
        assert turn.has_evidence is False

    def test_serialization(self) -> None:
        turn = ConversationTurn(user_input="test")
        d = asdict(turn)
        json_str = json.dumps(d, default=str)
        restored = json.loads(json_str)
        assert restored["user_input"] == "test"


class TestTaskLogEntry:
    def test_creation(self) -> None:
        entry = TaskLogEntry(turn_id="t1", stage="retrieval", status=TaskStatus.RUNNING)
        assert entry.status == TaskStatus.RUNNING
        assert entry.duration_ms == 0.0

    def test_metadata(self) -> None:
        entry = TaskLogEntry(
            turn_id="t1", stage="generation",
            metadata={"model": "test", "tokens": 100},
        )
        assert entry.metadata["model"] == "test"


class TestDocumentRecord:
    def test_default_status(self) -> None:
        doc = DocumentRecord(path="/test/file.py")
        assert doc.indexing_status == IndexingStatus.PENDING

    def test_serialization(self) -> None:
        doc = DocumentRecord(path="/test/file.py", size_bytes=1024)
        d = asdict(doc)
        json_str = json.dumps(d, default=str)
        assert "file.py" in json_str


class TestChunkRecord:
    def test_creation(self) -> None:
        chunk = ChunkRecord(
            document_id="d1", byte_start=0, byte_end=100,
            line_start=1, line_end=5, text="chunk text",
        )
        assert chunk.text == "chunk text"
        assert chunk.byte_end == 100
