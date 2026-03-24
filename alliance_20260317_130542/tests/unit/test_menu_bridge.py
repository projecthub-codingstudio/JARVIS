"""Tests for the menu bar JSON bridge payload."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from jarvis.cli.menu_bridge import (
    MenuBarTranscriptionResponse,
    _MAX_DISPLAY_CHARS,
    _build_navigation_window,
    _export_draft,
    _health_payload,
    _synthesize_speech,
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
    def test_serializes_turn_with_citations(self, tmp_path: Path) -> None:
        kb = tmp_path / "knowledge_base"
        kb.mkdir()
        (kb / "pipeline.py").write_text(
            "class Pipeline:\n    def run(self) -> None:\n        pass\n",
            encoding="utf-8",
        )
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
            knowledge_base_path=kb,
        )

        assert payload.query == "pipeline.py 설명해줘"
        assert payload.has_evidence is True
        assert payload.status is not None
        assert payload.status.mode == "normal"
        assert payload.citations[0].source_type == "code"
        assert payload.citations[0].label == "[1]"
        assert payload.render_hints is not None
        assert payload.render_hints.response_type == "grounded_code_answer"
        assert payload.render_hints.primary_source_type == "code"
        assert payload.render_hints.source_profile == "code"
        assert payload.render_hints.interaction_mode == "source_exploration"
        assert payload.render_hints.citation_count == 1
        assert payload.render_hints.truncated is False
        assert payload.exploration is not None
        assert payload.exploration.target_file == "pipeline.py"
        assert any(item.label == "Pipeline" for item in payload.exploration.class_candidates)
        assert any("class Pipeline" in item.preview for item in payload.exploration.class_candidates)

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
            knowledge_base_path=None,
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
            knowledge_base_path=None,
        )

        assert payload.citations == []
        assert payload.status is not None
        assert payload.status.mode == "no_evidence"
        assert payload.render_hints is not None
        assert payload.render_hints.response_type == "no_evidence"
        assert payload.render_hints.primary_source_type == "none"
        assert payload.render_hints.interaction_mode == "general_query"
        assert payload.render_hints.citation_count == 0

    def test_marks_document_exploration_mode_for_document_queries(self) -> None:
        kb = Path.cwd()
        evidence = VerifiedEvidenceSet(
            items=(
                EvidenceItem(
                    chunk_id="chunk-doc",
                    document_id="doc-doc",
                    text="보고서 요약 내용",
                    citation=CitationRecord(
                        document_id="doc-doc",
                        chunk_id="chunk-doc",
                        label="[1]",
                        state=CitationState.VALID,
                    ),
                    relevance_score=0.8,
                    source_path="/tmp/guide.pdf",
                ),
            ),
            query_fragments=(TypedQueryFragment(text="guide pdf", language="en", query_type="keyword"),),
        )
        payload = build_menu_response(
            turn=ConversationTurn(
                user_input="guide.pdf 문서를 요약해줘",
                assistant_output="문서 요약입니다. [1]",
                has_evidence=True,
            ),
            answer=AnswerDraft(content="문서 요약입니다. [1]", evidence=evidence, model_id="stub"),
            safe_mode=False,
            degraded_mode=False,
            generation_blocked=False,
            write_blocked=False,
            rebuild_index_required=False,
            knowledge_base_path=kb,
        )

        assert payload.render_hints is not None
        assert payload.render_hints.interaction_mode == "document_exploration"

    def test_builds_document_candidates_for_document_mode(self, tmp_path: Path) -> None:
        kb = tmp_path / "knowledge_base"
        kb.mkdir()
        (kb / "guide.pdf").write_text("JARVIS guide summary\nSection 1\nSection 2\n", encoding="utf-8")
        payload = build_menu_response(
            turn=ConversationTurn(
                user_input="guide.pdf 문서 요약해줘",
                assistant_output="문서 요약입니다.",
                has_evidence=False,
            ),
            answer=None,
            safe_mode=False,
            degraded_mode=False,
            generation_blocked=False,
            write_blocked=False,
            rebuild_index_required=False,
            knowledge_base_path=kb,
        )

        assert payload.exploration is not None
        assert payload.exploration.target_document == "guide.pdf"
        assert payload.exploration.document_candidates
        assert payload.exploration.document_candidates[0].preview.startswith("JARVIS guide summary")

    def test_build_navigation_window_returns_source_candidates(self, monkeypatch, tmp_path: Path) -> None:
        kb = tmp_path / "knowledge_base"
        kb.mkdir()
        (kb / "pipeline.py").write_text(
            "class Pipeline:\n    def run(self) -> None:\n        pass\n",
            encoding="utf-8",
        )
        monkeypatch.setattr("jarvis.cli.menu_bridge.resolve_knowledge_base_path", lambda _: kb)

        result = _build_navigation_window(
            query="파이포라인점 파이 클래스 보여줘",
            model_id="menu_bar",
        )

        assert result.mode == "source_exploration"
        assert result.file_candidates
        assert result.class_candidates

    def test_build_navigation_window_uses_lightweight_kb_resolution(self, monkeypatch, tmp_path: Path) -> None:
        kb = tmp_path / "knowledge_base"
        kb.mkdir()
        (kb / "pipeline.py").write_text("class Pipeline:\n    pass\n", encoding="utf-8")

        monkeypatch.setattr("jarvis.cli.menu_bridge.resolve_knowledge_base_path", lambda _: kb)
        monkeypatch.setattr(
            "jarvis.cli.menu_bridge._build_context",
            lambda model_id: (_ for _ in ()).throw(AssertionError("should not build runtime context")),
        )

        result = _build_navigation_window(
            query="pipeline.py 클래스 보여줘",
            model_id="menu_bar",
        )

        assert result.mode == "source_exploration"
        assert result.file_candidates[0].label == "pipeline.py"

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

    def test_synthesize_speech_returns_audio_path(self, monkeypatch, tmp_path: Path) -> None:
        class FakeTTS:
            def __init__(self, voice: str | None = None) -> None:
                self.voice = voice

            def synthesize(self, text: str, output_path: Path) -> Path:
                output_path.write_text(text, encoding="utf-8")
                return output_path

        monkeypatch.setattr("jarvis.cli.menu_bridge.LocalTTSRuntime", FakeTTS)
        monkeypatch.setattr("jarvis.cli.menu_bridge._TTS_DIR", tmp_path)

        result = _synthesize_speech(text="jarvis test")

        assert result.audio_path.endswith(".aiff")
        assert Path(result.audio_path).read_text(encoding="utf-8") == "jarvis test"

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
            knowledge_base_path=None,
        )
        assert payload.full_response_path == ""
        assert payload.response == "짧은 답변"
        assert payload.render_hints is not None
        assert payload.render_hints.truncated is False

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
            knowledge_base_path=None,
        )
        assert payload.response.endswith(" ...more")
        assert len(payload.response) == _MAX_DISPLAY_CHARS + len(" ...more")
        assert payload.full_response_path != ""
        assert payload.render_hints is not None
        assert payload.render_hints.truncated is True

        # Verify temp file contains full response
        full_content = Path(payload.full_response_path).read_text(encoding="utf-8")
        assert full_content == long_text
        # Cleanup
        Path(payload.full_response_path).unlink(missing_ok=True)

    def test_health_payload_exposes_lazy_and_disabled_runtime_states(self) -> None:
        class FakeEmbedding:
            is_loaded = False

            def _check_available(self) -> bool:
                return True

        class FakeVector:
            _embedding_runtime = FakeEmbedding()

            def _check_available(self) -> bool:
                return False

        class FakeReranker:
            _model = None

            def _check_available(self) -> bool:
                return False

        class FakeDB:
            def execute(self, _query: str) -> int:
                return 1

        context = SimpleNamespace(
            bootstrap_result=SimpleNamespace(
                db=FakeDB(),
                metrics=object(),
                config=SimpleNamespace(watched_folders=[Path.cwd()], export_dir=Path.cwd() / "exports"),
            ),
            orchestrator=SimpleNamespace(
                _llm_generator=SimpleNamespace(model_id="qwen3.5:9b"),
                _reranker=FakeReranker(),
            ),
            vector_index=FakeVector(),
            watcher=SimpleNamespace(is_alive=lambda: True),
            governor=SimpleNamespace(
                sample=lambda: SimpleNamespace(
                    thermal_state="nominal",
                    memory_pressure_pct=20.0,
                    swap_used_mb=0,
                    on_ac_power=True,
                    battery_pct=100,
                )
            ),
            chunk_count=12,
            knowledge_base_path=Path.cwd(),
        )

        payload = _health_payload(context=context)

        assert payload["checks"]["embeddings"] is True
        assert payload["details"]["embeddings"] == "ready (lazy-loaded)"
        assert payload["checks"]["vector_search"] is False
        assert payload["details"]["vector_search"] == "FTS-only mode"
        assert payload["checks"]["reranker"] is False
        assert payload["details"]["reranker"] == "disabled (cross-encoder unavailable)"
