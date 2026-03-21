"""Tests for the menu bar JSON bridge payload."""

from __future__ import annotations

from pathlib import Path

from jarvis.cli.menu_bridge import (
    MenuBarTranscriptionResponse,
    _MAX_DISPLAY_CHARS,
    _export_draft,
    build_menu_response,
)
from jarvis.contracts import (
    AnswerDraft,
    CitationRecord,
    CitationState,
    ConversationTurn,
    EvidenceItem,
    TypedQueryFragment,
    VerifiedEvidenceSet,
)


def _answer(*, model_id: str = "stub") -> AnswerDraft:
    evidence = VerifiedEvidenceSet(
        items=(
            EvidenceItem(
                chunk_id="chunk-1",
                document_id="doc-1",
                text="def run_pipeline(): return True",
                citation=CitationRecord(
                    document_id="doc-1",
                    chunk_id="chunk-1",
                    label="[1]",
                    state=CitationState.VALID,
                ),
                relevance_score=0.93,
                source_path="/tmp/pipeline.py",
            ),
        ),
        query_fragments=(TypedQueryFragment(text="pipeline", language="en", query_type="keyword"),),
    )
    return AnswerDraft(content="이 함수는 파이프라인을 실행합니다. [1]", evidence=evidence, model_id=model_id)


class TestMenuBridge:
    def test_serializes_turn_with_citations(self) -> None:
        payload = build_menu_response(
            turn=ConversationTurn(
                user_input="pipeline.py 설명해줘",
                assistant_output="이 함수는 파이프라인을 실행합니다. [1]",
                has_evidence=True,
            ),
            answer=_answer(),
            safe_mode=False,
            degraded_mode=False,
            generation_blocked=False,
            write_blocked=False,
            rebuild_index_required=False,
        )

        assert payload.query == "pipeline.py 설명해줘"
        assert payload.has_evidence is True
        assert payload.status is not None
        assert payload.status.mode == "normal"
        assert payload.citations[0].source_type == "code"
        assert payload.citations[0].label == "[1]"

    def test_marks_safe_mode_from_answer_model(self) -> None:
        payload = build_menu_response(
            turn=ConversationTurn(
                user_input="상태 알려줘",
                assistant_output="현재 시스템이 safe mode 상태입니다.",
                has_evidence=True,
            ),
            answer=_answer(model_id="safe_mode"),
            safe_mode=True,
            degraded_mode=True,
            generation_blocked=True,
            write_blocked=False,
            rebuild_index_required=False,
        )

        assert payload.status is not None
        assert payload.status.mode == "safe_mode"
        assert payload.status.safe_mode is True
        assert payload.status.generation_blocked is True

    def test_marks_no_evidence_without_answer(self) -> None:
        payload = build_menu_response(
            turn=ConversationTurn(
                user_input="없는 파일 찾아줘",
                assistant_output="관련 증거를 찾을 수 없어 답변을 생성할 수 없습니다.",
                has_evidence=False,
            ),
            answer=None,
            safe_mode=False,
            degraded_mode=False,
            generation_blocked=False,
            write_blocked=False,
            rebuild_index_required=False,
        )

        assert payload.citations == []
        assert payload.status is not None
        assert payload.status.mode == "no_evidence"

    def test_export_draft_requires_explicit_approval(self, tmp_path: Path) -> None:
        destination = tmp_path / "draft.txt"

        result = _export_draft(
            content="초안 본문",
            destination=destination,
            approved=False,
        )

        assert result.success is False
        assert result.approved is False
        assert destination.exists() is False

    def test_export_draft_writes_after_approval(self, tmp_path: Path) -> None:
        destination = tmp_path / "draft.txt"

        result = _export_draft(
            content="초안 본문",
            destination=destination,
            approved=True,
        )

        assert result.success is True
        assert result.approved is True
        assert destination.read_text(encoding="utf-8") == "초안 본문"

    def test_transcription_payload_serializes_text(self) -> None:
        payload = MenuBarTranscriptionResponse(transcript="회의 일정 정리해 줘")
        assert payload.transcript == "회의 일정 정리해 줘"

    def test_short_response_has_no_full_path(self) -> None:
        payload = build_menu_response(
            turn=ConversationTurn(
                user_input="짧은 질문",
                assistant_output="짧은 답변",
                has_evidence=False,
            ),
            answer=None,
            safe_mode=False,
            degraded_mode=False,
            generation_blocked=False,
            write_blocked=False,
            rebuild_index_required=False,
        )
        assert payload.full_response_path == ""
        assert payload.response == "짧은 답변"

    def test_long_response_truncated_with_temp_file(self) -> None:
        long_text = "가" * (_MAX_DISPLAY_CHARS + 200)
        payload = build_menu_response(
            turn=ConversationTurn(
                user_input="긴 질문",
                assistant_output=long_text,
                has_evidence=False,
            ),
            answer=None,
            safe_mode=False,
            degraded_mode=False,
            generation_blocked=False,
            write_blocked=False,
            rebuild_index_required=False,
        )
        assert payload.response.endswith(" ...more")
        assert len(payload.response) == _MAX_DISPLAY_CHARS + len(" ...more")
        assert payload.full_response_path != ""

        # Verify temp file contains full response
        full_content = Path(payload.full_response_path).read_text(encoding="utf-8")
        assert full_content == long_text
        # Cleanup
        Path(payload.full_response_path).unlink(missing_ok=True)
