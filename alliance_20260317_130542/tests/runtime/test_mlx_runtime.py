"""Tests for MLXRuntime generation behavior."""

from __future__ import annotations

from jarvis.contracts import CitationRecord, EvidenceItem, VerifiedEvidenceSet
from jarvis.runtime.mlx_runtime import MLXRuntime, strip_think_tags


class _Backend:
    model_id = "stub-backend"

    def generate(self, prompt: str, context: str, intent: str) -> str:
        return (
            "JARVIS uses SQLite FTS5 and LanceDB hybrid retrieval. "
            "It also controls every macOS application automatically."
        )


def _evidence_set() -> VerifiedEvidenceSet:
    item = EvidenceItem(
        chunk_id="c1",
        document_id="d1",
        text="JARVIS uses SQLite FTS5 and LanceDB hybrid retrieval for grounded answers.",
        citation=CitationRecord(document_id="d1", chunk_id="c1", label="[1]"),
        source_path="/tmp/architecture.md",
        relevance_score=1.0,
    )
    return VerifiedEvidenceSet(items=(item,), query_fragments=())


class TestMLXRuntime:
    def test_exposes_backend_model_id_for_health_checks(self) -> None:
        runtime = MLXRuntime(backend=_Backend(), model_id="stub")

        assert runtime.model_id == "stub-backend"

    def test_generate_records_verification_warnings(self) -> None:
        runtime = MLXRuntime(backend=_Backend())

        answer = runtime.generate("설명해줘", _evidence_set())

        assert len(answer.verification_warnings) == 1
        assert "근거 정렬 미확인 문장" in answer.verification_warnings[0]


class TestStripThinkTags:
    def test_removes_think_block(self) -> None:
        raw = "<think>내부 추론 내용</think>\n실제 답변입니다."
        assert strip_think_tags(raw) == "실제 답변입니다."

    def test_removes_multiline_think_block(self) -> None:
        raw = "<think>\nstep 1\nstep 2\nstep 3\n</think>\n답변 내용"
        assert strip_think_tags(raw) == "답변 내용"

    def test_no_think_tags_unchanged(self) -> None:
        text = "일반 텍스트 응답"
        assert strip_think_tags(text) == text

    def test_empty_think_block(self) -> None:
        raw = "<think></think>결과"
        assert strip_think_tags(raw) == "결과"

    def test_backend_response_stripped_in_generate(self) -> None:
        """Think tags are stripped before AnswerDraft is created."""

        class _ThinkBackend:
            model_id = "think-model"

            def generate(self, prompt: str, context: str, intent: str) -> str:
                return "<think>reasoning here</think>\n실제 답변"

        runtime = MLXRuntime(backend=_ThinkBackend())
        answer = runtime.generate("테스트", _evidence_set())
        assert "<think>" not in answer.content
        assert answer.content == "실제 답변"
