"""Tests for streaming LLM response pipeline."""
from __future__ import annotations

from collections.abc import Iterator

import pytest

from jarvis.contracts import (
    AnswerDraft,
    CitationRecord,
    CitationState,
    ConversationTurn,
    EvidenceItem,
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
from jarvis.runtime.mlx_runtime import MLXRuntime, strip_think_tags


class FakeStreamingBackend:
    """Fake backend that supports generate_stream()."""

    model_id = "fake-streaming"

    def generate(self, prompt: str, context: str, intent: str) -> str:
        return "Full response text."

    def generate_stream(self, prompt: str, context: str, intent: str) -> Iterator[str]:
        for word in ["Hello", " ", "world", "!"]:
            yield word


class FakeStreamingWithThink:
    """Fake backend that emits think tags in stream."""

    model_id = "fake-think"

    def generate(self, prompt: str, context: str, intent: str) -> str:
        return "Answer after thinking."

    def generate_stream(self, prompt: str, context: str, intent: str) -> Iterator[str]:
        yield "<think>"
        yield "internal reasoning"
        yield "</think>"
        yield "Answer"
        yield " after"
        yield " thinking."


def make_evidence() -> VerifiedEvidenceSet:
    item = EvidenceItem(
        chunk_id="chunk-1",
        document_id="doc-1",
        text="streaming evidence",
        citation=CitationRecord(
            document_id="doc-1",
            chunk_id="chunk-1",
            label="[1]",
            state=CitationState.VALID,
        ),
        relevance_score=1.0,
        source_path="/tmp/doc.md",
    )
    return VerifiedEvidenceSet(items=(item,), query_fragments=())


class StaticEvidenceBuilder:
    def build(self, results, fragments) -> VerifiedEvidenceSet:
        return VerifiedEvidenceSet(items=make_evidence().items, query_fragments=tuple(fragments))


class StaticFTSRetriever:
    def search(self, fragments, top_k: int = 10):
        return []


class TestMLXRuntimeStream:
    def test_generate_stream_yields_tokens_then_answer(self) -> None:
        runtime = MLXRuntime(backend=FakeStreamingBackend())
        evidence = VerifiedEvidenceSet(items=(), query_fragments=())

        # With empty evidence, should yield AnswerDraft directly
        items = list(runtime.generate_stream("test", evidence))
        assert len(items) == 1
        assert isinstance(items[0], AnswerDraft)

    def test_generate_stream_with_explicit_evidence(self) -> None:
        runtime = MLXRuntime(backend=FakeStreamingBackend())
        evidence = make_evidence()

        tokens: list[str] = []
        answer: AnswerDraft | None = None
        for item in runtime.generate_stream("test query", evidence):
            if isinstance(item, str):
                tokens.append(item)
            else:
                answer = item

        assert len(tokens) > 0
        assert answer is not None
        assert isinstance(answer, AnswerDraft)

    def test_generate_stream_filters_think_tags(self) -> None:
        """Think tags should be suppressed in streaming output."""
        runtime = MLXRuntime(backend=FakeStreamingWithThink())
        evidence = make_evidence()

        tokens: list[str] = []
        for item in runtime.generate_stream("test", evidence):
            if isinstance(item, str):
                tokens.append(item)

        streamed_text = "".join(tokens)
        assert "<think>" not in streamed_text
        assert "internal reasoning" not in streamed_text
        assert "Answer" in streamed_text


class TestOrchestratorStream:
    @pytest.fixture
    def streaming_orchestrator(self) -> Orchestrator:
        return Orchestrator(
            governor=GovernorStub(),
            query_decomposer=QueryDecomposer(),
            fts_retriever=StaticFTSRetriever(),
            vector_retriever=VectorIndex(),
            hybrid_fusion=HybridSearch(),
            evidence_builder=StaticEvidenceBuilder(),
            llm_generator=MLXRuntime(backend=FakeStreamingBackend()),
            tool_registry=ToolRegistry(),
            conversation_store=ConversationStore(),
            task_log_store=TaskLogStore(),
        )

    def test_handle_turn_stream_yields_tokens_then_turn(
        self, streaming_orchestrator: Orchestrator,
    ) -> None:
        tokens: list[str] = []
        turn: ConversationTurn | None = None

        for item in streaming_orchestrator.handle_turn_stream("테스트 질문"):
            if isinstance(item, str):
                tokens.append(item)
            else:
                turn = item

        assert len(tokens) > 0, "Should yield at least one token"
        assert turn is not None, "Should yield a ConversationTurn at the end"
        assert isinstance(turn, ConversationTurn)
        assert turn.has_evidence is True

    def test_handle_turn_stream_destructive_yields_turn_only(
        self, streaming_orchestrator: Orchestrator,
    ) -> None:
        items = list(streaming_orchestrator.handle_turn_stream("파일 전부 삭제해줘"))
        assert len(items) == 1
        assert isinstance(items[0], ConversationTurn)
        assert items[0].has_evidence is False

    def test_handle_turn_stream_saves_conversation(
        self, streaming_orchestrator: Orchestrator,
    ) -> None:
        # Consume the stream
        for _ in streaming_orchestrator.handle_turn_stream("대화 저장 테스트"):
            pass

        store = streaming_orchestrator._conversation_store
        turns = store.get_recent_turns()
        assert len(turns) == 1

    def test_last_answer_available_after_stream(
        self, streaming_orchestrator: Orchestrator,
    ) -> None:
        for _ in streaming_orchestrator.handle_turn_stream("답변 테스트"):
            pass
        assert streaming_orchestrator.last_answer is not None


class TestStripThinkTags:
    def test_strip_simple(self) -> None:
        assert strip_think_tags("<think>hello</think>world") == "world"

    def test_strip_multiline(self) -> None:
        text = "<think>\nline1\nline2\n</think>\nAnswer here"
        assert strip_think_tags(text) == "Answer here"

    def test_no_tags(self) -> None:
        assert strip_think_tags("no tags here") == "no tags here"
