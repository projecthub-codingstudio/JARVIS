"""Tests for REPL rendering."""

from __future__ import annotations

from jarvis.cli.repl import JarvisREPL
from jarvis.contracts import AnswerDraft, CitationRecord, EvidenceItem, VerifiedEvidenceSet


def _answer_with_warning() -> AnswerDraft:
    item = EvidenceItem(
        chunk_id="c1",
        document_id="d1",
        text="JARVIS uses SQLite FTS5 and LanceDB hybrid retrieval for grounded answers.",
        citation=CitationRecord(document_id="d1", chunk_id="c1", label="[1]"),
        source_path="/tmp/architecture.md",
        relevance_score=1.0,
    )
    evidence = VerifiedEvidenceSet(items=(item,), query_fragments=())
    return AnswerDraft(
        content="응답 본문 [1]",
        evidence=evidence,
        verification_warnings=("근거 미확인: 테스트 문장",),
    )


class _Orchestrator:
    last_answer = None


class TestJarvisREPL:
    def test_display_response_shows_verification_warning(self, capsys) -> None:
        repl = JarvisREPL(_Orchestrator())

        repl._display_response("응답 본문", answer=_answer_with_warning())

        captured = capsys.readouterr().out
        assert "검증 경고" in captured
        assert "근거 미확인" in captured
