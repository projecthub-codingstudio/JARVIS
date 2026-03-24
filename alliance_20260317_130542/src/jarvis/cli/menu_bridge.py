"""JSON bridge between the Python core and the macOS menu bar app."""

from __future__ import annotations

import argparse
import json
import logging
import sys
import tempfile
import time
import traceback
from dataclasses import asdict, dataclass, field
from pathlib import Path

from jarvis.app.runtime_context import (
    build_runtime_context,
    resolve_knowledge_base_path,
    shutdown_runtime_context,
)
from jarvis.cli.voice_session import VoiceSession
from jarvis.contracts import (
    AnswerDraft,
    ConversationTurn,
    DraftExportRequest,
    DraftExportResult,
    EvidenceItem,
    VerifiedEvidenceSet,
)
from jarvis.identifier_restoration import build_identifier_lexicon, score_identifier_candidates
from jarvis.query_normalization import normalize_spoken_code_query

from jarvis.runtime.audio_recorder import AudioRecorder
from jarvis.observability.health import check_health
from jarvis.observability.logging import configure_logging
from jarvis.runtime.stt_biasing import build_vocabulary_hint
from jarvis.runtime.stt_runtime import WhisperCppSTT
from jarvis.runtime.tts_runtime import LocalTTSRuntime
from jarvis.tools.draft_export import DraftExportTool

_MAX_QUOTE_CHARS = 160
_MAX_DISPLAY_CHARS = 500
_RESPONSE_DIR = Path(tempfile.gettempdir()) / "jarvis_responses"
_TTS_DIR = Path(tempfile.gettempdir()) / "jarvis_tts"


def _detect_source_type(path: str) -> str:
    code_exts = {".py", ".ts", ".tsx", ".js", ".jsx", ".yaml", ".yml", ".json", ".sql"}
    suffix = Path(path).suffix.lower()
    return "code" if suffix in code_exts else "document"


def _quote_for(item: EvidenceItem) -> str:
    text = item.text.strip().replace("\n", " ")
    if len(text) > _MAX_QUOTE_CHARS:
        return text[:_MAX_QUOTE_CHARS] + "..."
    return text


def _response_mode(turn: ConversationTurn, answer: AnswerDraft | None) -> str:
    if answer is not None and answer.model_id == "safe_mode":
        return "safe_mode"
    if answer is not None and answer.model_id == "degraded":
        return "degraded"
    if "리소스가 부족" in turn.assistant_output:
        return "resource_blocked"
    if not turn.has_evidence:
        return "no_evidence"
    return "normal"


@dataclass(frozen=True)
class MenuBarCitation:
    label: str
    source_path: str
    source_type: str
    quote: str
    state: str
    relevance_score: float


@dataclass(frozen=True)
class MenuBarStatus:
    mode: str
    safe_mode: bool
    degraded_mode: bool
    generation_blocked: bool
    write_blocked: bool
    rebuild_index_required: bool


@dataclass(frozen=True)
class MenuBarRenderHints:
    response_type: str
    primary_source_type: str
    source_profile: str
    interaction_mode: str
    citation_count: int
    truncated: bool


@dataclass(frozen=True)
class MenuBarExplorationItem:
    label: str
    kind: str
    path: str
    score: float
    preview: str = ""


@dataclass(frozen=True)
class MenuBarExplorationState:
    mode: str
    target_file: str = ""
    target_document: str = ""
    file_candidates: list[MenuBarExplorationItem] = field(default_factory=list)
    document_candidates: list[MenuBarExplorationItem] = field(default_factory=list)
    class_candidates: list[MenuBarExplorationItem] = field(default_factory=list)
    function_candidates: list[MenuBarExplorationItem] = field(default_factory=list)


@dataclass(frozen=True)
class MenuBarResponse:
    query: str
    response: str
    has_evidence: bool
    citations: list[MenuBarCitation] = field(default_factory=list)
    status: MenuBarStatus | None = None
    render_hints: MenuBarRenderHints | None = None
    exploration: MenuBarExplorationState | None = None
    full_response_path: str = ""


@dataclass(frozen=True)
class MenuBarExportResponse:
    destination: str
    approved: bool
    success: bool
    error_message: str = ""


@dataclass(frozen=True)
class MenuBarTranscriptionResponse:
    transcript: str


@dataclass(frozen=True)
class MenuBarSpeechResponse:
    audio_path: str


@dataclass(frozen=True)
class MenuBarNormalizationResponse:
    normalized_query: str


@dataclass(frozen=True)
class MenuBarCommandEnvelope:
    kind: str
    query_result: MenuBarResponse | None = None
    navigation_result: MenuBarExplorationState | None = None
    normalization_result: MenuBarNormalizationResponse | None = None
    export_result: MenuBarExportResponse | None = None
    transcription_result: MenuBarTranscriptionResponse | None = None
    speech_result: MenuBarSpeechResponse | None = None
    health_result: dict[str, object] | None = None
    error: str = ""


def build_menu_response(
    *,
    turn: ConversationTurn,
    answer: AnswerDraft | None,
    safe_mode: bool,
    degraded_mode: bool,
    generation_blocked: bool,
    write_blocked: bool,
    rebuild_index_required: bool,
    knowledge_base_path: Path | None = None,
) -> MenuBarResponse:
    """Serialize a completed turn into a menu bar-friendly payload."""
    citations: list[MenuBarCitation] = []
    if answer is not None:
        # Evidence items already passed retrieval + reranking filters.
        # No additional threshold — reranker scores use a different scale.
        for item in answer.evidence.items[:5]:
            full_path = item.source_path or item.document_id
            display_name = Path(full_path).name if full_path else item.document_id
            citations.append(MenuBarCitation(
                label=item.citation.label,
                source_path=display_name,
                source_type=_detect_source_type(full_path),
                quote=_quote_for(item),
                state=item.citation.state.value,
                relevance_score=item.relevance_score,
            ))

    mode = _response_mode(turn, answer)

    full_text = turn.assistant_output
    full_response_path = ""
    display_text = full_text

    if len(full_text) > _MAX_DISPLAY_CHARS:
        _RESPONSE_DIR.mkdir(parents=True, exist_ok=True)
        ts = int(time.time() * 1000)
        response_file = _RESPONSE_DIR / f"response_{ts}.txt"
        response_file.write_text(full_text, encoding="utf-8")
        full_response_path = str(response_file)
        display_text = full_text[:_MAX_DISPLAY_CHARS] + " ...more"

    citation_count = len(citations)
    source_types = {citation.source_type for citation in citations}
    if not source_types:
        primary_source_type = "none"
        source_profile = "none"
    elif len(source_types) == 1:
        primary_source_type = next(iter(source_types))
        source_profile = primary_source_type
    else:
        primary_source_type = "mixed"
        source_profile = "mixed"

    if mode in {"safe_mode", "degraded", "resource_blocked"}:
        response_type = "runtime_status"
    elif mode == "no_evidence":
        response_type = "no_evidence"
    elif citation_count > 0 and primary_source_type == "code":
        response_type = "grounded_code_answer"
    elif citation_count > 0:
        response_type = "grounded_document_answer"
    else:
        response_type = "plain_answer"

    interaction_mode = _detect_interaction_mode(
        query=turn.user_input,
        response_type=response_type,
        primary_source_type=primary_source_type,
    )
    exploration = _build_exploration_state(
        query=turn.user_input,
        interaction_mode=interaction_mode,
        knowledge_base_path=knowledge_base_path,
    )

    return MenuBarResponse(
        query=turn.user_input,
        response=display_text,
        has_evidence=turn.has_evidence,
        citations=citations,
        status=MenuBarStatus(
            mode=mode,
            safe_mode=safe_mode,
            degraded_mode=degraded_mode,
            generation_blocked=generation_blocked,
            write_blocked=write_blocked,
            rebuild_index_required=rebuild_index_required,
        ),
        render_hints=MenuBarRenderHints(
            response_type=response_type,
            primary_source_type=primary_source_type,
            source_profile=source_profile,
            interaction_mode=interaction_mode,
            citation_count=citation_count,
            truncated=bool(full_response_path),
        ),
        exploration=exploration,
        full_response_path=full_response_path,
    )


def _detect_interaction_mode(*, query: str, response_type: str, primary_source_type: str) -> str:
    lowered = query.lower()
    code_markers = (
        "소스", "코드", "클래스", "함수", "메서드", "메소드", "python", "class", "function", "method",
        ".py", ".ts", ".js", ".tsx", ".jsx", "import ", "def ",
    )
    document_markers = (
        "문서", "pdf", "ppt", "pptx", "doc", "docx", "보고서", "매뉴얼", "가이드", "요약", "정리",
    )
    if primary_source_type == "code" or response_type == "grounded_code_answer":
        return "source_exploration"
    if any(marker in lowered for marker in code_markers):
        return "source_exploration"
    if primary_source_type == "document" or response_type == "grounded_document_answer":
        return "document_exploration"
    if any(marker in lowered for marker in document_markers):
        return "document_exploration"
    return "general_query"


def _build_exploration_state(
    *,
    query: str,
    interaction_mode: str,
    knowledge_base_path: Path | None,
) -> MenuBarExplorationState | None:
    if interaction_mode == "document_exploration":
        return _build_document_exploration_state(query=query, knowledge_base_path=knowledge_base_path)
    if interaction_mode != "source_exploration":
        return None
    lexicon = build_identifier_lexicon(knowledge_base_path)
    if not lexicon:
        return MenuBarExplorationState(mode=interaction_mode)
    entries_by_key = {(entry.canonical, entry.kind): entry for entry in lexicon}
    scored = score_identifier_candidates(query, lexicon, limit=8)

    files: list[MenuBarExplorationItem] = []
    classes: list[MenuBarExplorationItem] = []
    functions: list[MenuBarExplorationItem] = []
    target_file = ""
    for candidate in scored:
        entry = entries_by_key.get((candidate.canonical, candidate.kind))
        if entry is None:
            continue
        item = MenuBarExplorationItem(
            label=entry.canonical,
            kind=entry.kind,
            path=entry.path,
            score=round(candidate.score, 3),
            preview=_preview_for_entry(entry, knowledge_base_path),
        )
        if entry.kind == "filename":
            files.append(item)
            if not target_file and entry.canonical.endswith((".py", ".ts", ".tsx", ".js", ".jsx", ".sql")):
                target_file = entry.canonical
        elif entry.kind == "class":
            classes.append(item)
        elif entry.kind == "function":
            functions.append(item)
    return MenuBarExplorationState(
        mode=interaction_mode,
        target_file=target_file,
        file_candidates=files[:4],
        class_candidates=classes[:4],
        function_candidates=functions[:4],
    )


def _build_document_exploration_state(
    *,
    query: str,
    knowledge_base_path: Path | None,
) -> MenuBarExplorationState | None:
    if knowledge_base_path is None or not knowledge_base_path.exists():
        return MenuBarExplorationState(mode="document_exploration")

    query_words = {
        word.lower() for word in query.replace("/", " ").replace("-", " ").split()
        if len(word) > 1
    }
    candidates: list[MenuBarExplorationItem] = []
    document_exts = {".pdf", ".md", ".txt", ".docx", ".pptx", ".xlsx", ".hwp", ".hwpx"}
    for path in sorted(knowledge_base_path.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in document_exts:
            continue
        score = 0.2
        name = path.name.lower()
        stem_words = set(path.stem.lower().replace("-", " ").replace("_", " ").split())
        overlap = query_words & (stem_words | {name})
        score += min(0.6, len(overlap) * 0.18)
        preview = _preview_document(path)
        candidates.append(MenuBarExplorationItem(
            label=path.name,
            kind="document",
            path=path.relative_to(knowledge_base_path).as_posix(),
            score=round(score, 3),
            preview=preview,
        ))
    ranked = sorted(candidates, key=lambda item: (item.score, item.label), reverse=True)[:4]
    target_document = ranked[0].label if ranked else ""
    return MenuBarExplorationState(
        mode="document_exploration",
        target_document=target_document,
        document_candidates=ranked,
    )


def _preview_for_entry(entry: object, knowledge_base_path: Path | None) -> str:
    if knowledge_base_path is None or not getattr(entry, "path", ""):
        return ""
    file_path = knowledge_base_path / entry.path
    try:
        text = file_path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""

    if getattr(entry, "kind", "") == "filename":
        lines = text.splitlines()
        return "\n".join(lines[:18]).strip()[:1200]

    canonical = getattr(entry, "canonical", "")
    if getattr(entry, "kind", "") == "class":
        pattern = rf"^\s*class\s+{canonical}\b.*$"
    elif getattr(entry, "kind", "") == "function":
        pattern = rf"^\s*def\s+{canonical}\b.*$"
    else:
        pattern = rf"\b{canonical}\b"

    match = __import__("re").search(pattern, text, __import__("re").MULTILINE)
    if match is None:
        return ""
    before = text[:match.start()].splitlines()
    after = text[match.start():].splitlines()
    start_line = max(0, len(before))
    lines = text.splitlines()
    preview_lines = lines[start_line:start_line + 18]
    return "\n".join(preview_lines).strip()[:1200]


def _preview_document(path: Path) -> str:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return "\n".join(lines[:18])[:1200]


def _build_context(*, model_id: str):
    return build_runtime_context(
        model_id=model_id,
        start_watcher_enabled=True,
        start_background_backfill=False,
        allow_mlx=True,
        data_dir=Path.cwd() / ".jarvis-menubar",
    )


def _resolve_bridge_knowledge_base_path() -> Path | None:
    path = resolve_knowledge_base_path(None)
    return path if path.exists() else None


def _response_from_context(*, context: object, turn: ConversationTurn) -> MenuBarResponse:
    answer = context.orchestrator.last_answer
    return build_menu_response(
        turn=turn,
        answer=answer,
        safe_mode=context.error_monitor.safe_mode_active(),
        degraded_mode=context.error_monitor.degraded_mode,
        generation_blocked=context.error_monitor.generation_blocked,
        write_blocked=context.error_monitor.write_blocked,
        rebuild_index_required=context.error_monitor.rebuild_index_required,
        knowledge_base_path=context.knowledge_base_path,
    )


def _build_navigation_window(*, query: str, model_id: str) -> MenuBarExplorationState:
    del model_id
    interaction_mode = _detect_interaction_mode(
        query=query,
        response_type="plain_answer",
        primary_source_type="none",
    )
    exploration = _build_exploration_state(
        query=query,
        interaction_mode=interaction_mode,
        knowledge_base_path=_resolve_bridge_knowledge_base_path(),
    )
    return exploration or MenuBarExplorationState(mode=interaction_mode)


def _normalize_query(*, query: str) -> MenuBarNormalizationResponse:
    return MenuBarNormalizationResponse(
        normalized_query=normalize_spoken_code_query(
            query,
            knowledge_base_path=_resolve_bridge_knowledge_base_path(),
        )
    )


def _run_query(*, query: str, model_id: str) -> MenuBarResponse:
    context = _build_context(model_id=model_id)
    try:
        turn = context.orchestrator.handle_turn(query)
        return _response_from_context(context=context, turn=turn)
    finally:
        shutdown_runtime_context(context)


def _record_once(*, model_id: str, device: str | None = None) -> MenuBarResponse:
    context = _build_context(model_id=model_id)
    try:
        stt_runtime = WhisperCppSTT(
            model_path=(
                Path(model_path).expanduser()
                if (model_path := __import__("os").getenv("JARVIS_STT_MODEL"))
                else None
            ),
            model_router=context.model_router,
            vocabulary_hint=build_vocabulary_hint(context.knowledge_base_path),
        )
        tts_runtime = LocalTTSRuntime(
            voice=__import__("os").getenv("JARVIS_TTS_VOICE"),
            model_router=context.model_router,
        )
        recorder = AudioRecorder(
            input_device=device,
            duration_seconds=int(__import__("os").getenv("JARVIS_PTT_SECONDS", "8"))
        )
        session = VoiceSession(
            orchestrator=context.orchestrator,
            stt_runtime=stt_runtime,
            tts_runtime=tts_runtime,
            recorder=recorder,
        )
        turn = session.record_and_handle_once()
        return _response_from_context(context=context, turn=turn)
    finally:
        shutdown_runtime_context(context)


def _transcribe_once(*, model_id: str, device: str | None = None) -> MenuBarTranscriptionResponse:
    context = _build_context(model_id=model_id)
    try:
        stt_runtime = WhisperCppSTT(
            model_path=(
                Path(model_path).expanduser()
                if (model_path := __import__("os").getenv("JARVIS_STT_MODEL"))
                else None
            ),
            model_router=context.model_router,
            vocabulary_hint=build_vocabulary_hint(context.knowledge_base_path),
        )
        recorder = AudioRecorder(
            input_device=device,
            duration_seconds=int(__import__("os").getenv("JARVIS_PTT_SECONDS", "8"))
        )
        session = VoiceSession(
            orchestrator=context.orchestrator,
            stt_runtime=stt_runtime,
            recorder=recorder,
        )
        return MenuBarTranscriptionResponse(transcript=session.record_and_transcribe_once())
    finally:
        shutdown_runtime_context(context)


def _transcribe_file(*, audio_path: str) -> MenuBarTranscriptionResponse:
    """Transcribe a pre-recorded audio file via whisper-cli (no microphone access needed)."""
    path = Path(audio_path).expanduser().resolve()
    if not path.exists():
        raise RuntimeError(f"오디오 파일을 찾을 수 없습니다: {path}")

    stt_runtime = WhisperCppSTT(
        model_path=(
            Path(model_path).expanduser()
            if (model_path := __import__("os").getenv("JARVIS_STT_MODEL"))
            else None
        ),
    )
    transcript = stt_runtime.transcribe(path).strip()
    if not transcript:
        raise RuntimeError("음성이 감지되지 않았습니다. 마이크에 대고 다시 말씀해 주세요.")
    return MenuBarTranscriptionResponse(transcript=transcript)


def _synthesize_speech(*, text: str) -> MenuBarSpeechResponse:
    clean_text = text.strip()
    if not clean_text:
        raise RuntimeError("음성 합성할 텍스트가 비어 있습니다.")

    tts_runtime = LocalTTSRuntime(
        voice=__import__("os").getenv("JARVIS_TTS_VOICE"),
    )
    _TTS_DIR.mkdir(parents=True, exist_ok=True)
    output_path = _TTS_DIR / f"speech_{int(time.time() * 1000)}.aiff"
    result = tts_runtime.synthesize(clean_text, output_path)
    return MenuBarSpeechResponse(audio_path=str(result))


def _record_once_in_context(*, context: object, device: str | None = None) -> MenuBarResponse:
    stt_runtime = WhisperCppSTT(
        model_path=(
            Path(model_path).expanduser()
            if (model_path := __import__("os").getenv("JARVIS_STT_MODEL"))
            else None
        ),
        model_router=context.model_router,
        vocabulary_hint=build_vocabulary_hint(context.knowledge_base_path),
    )
    tts_runtime = LocalTTSRuntime(
        voice=__import__("os").getenv("JARVIS_TTS_VOICE"),
        model_router=context.model_router,
    )
    recorder = AudioRecorder(
        input_device=device,
        duration_seconds=int(__import__("os").getenv("JARVIS_PTT_SECONDS", "8"))
    )
    session = VoiceSession(
        orchestrator=context.orchestrator,
        stt_runtime=stt_runtime,
        tts_runtime=tts_runtime,
        recorder=recorder,
    )
    turn = session.record_and_handle_once()
    return _response_from_context(context=context, turn=turn)


def _record_once_stream_in_context(*, context: object, device: str | None = None) -> ConversationTurn | None:
    """Record once with streaming tokens sent as stream_chunk JSON."""
    stt_runtime = WhisperCppSTT(
        model_path=(
            Path(model_path).expanduser()
            if (model_path := __import__("os").getenv("JARVIS_STT_MODEL"))
            else None
        ),
        model_router=context.model_router,
        vocabulary_hint=build_vocabulary_hint(context.knowledge_base_path),
    )
    recorder = AudioRecorder(
        input_device=device,
        duration_seconds=int(__import__("os").getenv("JARVIS_PTT_SECONDS", "8"))
    )
    session = VoiceSession(
        orchestrator=context.orchestrator,
        stt_runtime=stt_runtime,
        recorder=recorder,
    )

    def _emit_token(token: str) -> None:
        print(json.dumps({"kind": "stream_chunk", "token": token}, ensure_ascii=False), flush=True)

    return session.record_and_handle_once_stream(on_token=_emit_token)


def _transcribe_once_in_context(*, context: object, device: str | None = None) -> MenuBarTranscriptionResponse:
    stt_runtime = WhisperCppSTT(
        model_path=(
            Path(model_path).expanduser()
            if (model_path := __import__("os").getenv("JARVIS_STT_MODEL"))
            else None
        ),
        model_router=context.model_router,
    )
    recorder = AudioRecorder(
        input_device=device,
        duration_seconds=int(__import__("os").getenv("JARVIS_PTT_SECONDS", "8"))
    )
    session = VoiceSession(
        orchestrator=context.orchestrator,
        stt_runtime=stt_runtime,
        recorder=recorder,
    )
    return MenuBarTranscriptionResponse(transcript=session.record_and_transcribe_once())


def _export_draft(
    *,
    content: str,
    destination: Path,
    approved: bool,
) -> MenuBarExportResponse:
    class _MenuBarApprovalGateway:
        def __init__(self, *, approved: bool) -> None:
            self._approved = approved

        def request_approval(self, request: DraftExportRequest) -> bool:
            return self._approved

        def execute_export(self, request: DraftExportRequest) -> DraftExportResult:
            if not self._approved:
                return DraftExportResult(
                    success=False,
                    destination=request.destination,
                    approved=False,
                    error_message="Approval pending",
                )
            request.destination.parent.mkdir(parents=True, exist_ok=True)
            request.destination.write_text(request.draft.content, encoding="utf-8")
            return DraftExportResult(
                success=True,
                destination=request.destination,
                approved=True,
            )

    tool = DraftExportTool(approval_gateway=_MenuBarApprovalGateway(approved=approved))
    request = DraftExportRequest(
        draft=AnswerDraft(
            content=content,
            evidence=VerifiedEvidenceSet(items=(), query_fragments=()),
            model_id="menu_bar",
        ),
        destination=destination,
    )
    result = tool.execute(request=request)
    return MenuBarExportResponse(
        destination=str(destination),
        approved=result.approved,
        success=result.success,
        error_message=result.error_message,
    )


def _health_payload(*, context: object) -> dict[str, object]:
    health_deps = {
        "db": context.bootstrap_result.db,
        "metrics": context.bootstrap_result.metrics,
        "config": context.bootstrap_result.config,
        "llm_generator": context.orchestrator._llm_generator,
        "embedding_runtime": context.vector_index._embedding_runtime,
        "vector_index": context.vector_index,
        "reranker": context.orchestrator._reranker,
        "file_watcher": context.watcher,
        "governor": context.governor,
    }
    status = check_health(health_deps)
    checks = dict(status.checks)
    details = dict(status.details)
    checks["knowledge_base"] = context.knowledge_base_path is not None
    details["knowledge_base"] = (
        str(context.knowledge_base_path) if context.knowledge_base_path is not None else "not configured"
    )
    vector_available = context.vector_index._check_available()
    checks["vector_search"] = vector_available
    details["vector_search"] = "active" if vector_available else "FTS-only mode"

    failed_checks = list(status.failed_checks)
    if not checks["knowledge_base"]:
        failed_checks.append("knowledge_base")
    if not checks["vector_search"]:
        failed_checks.append("vector_search")
    return {
        "healthy": status.healthy,
        "message": status.message,
        "checks": checks,
        "details": details,
        "failed_checks": failed_checks,
        "status_level": "healthy" if not failed_checks else ("warning" if len(failed_checks) <= 2 else "degraded"),
        "chunk_count": context.chunk_count,
        "knowledge_base_path": str(context.knowledge_base_path) if context.knowledge_base_path else "",
        "bridge_mode": "persistent",
    }


def _health_light() -> dict[str, object]:
    """Lightweight health check — no LLM loading, no embedding backfill.

    Only opens the SQLite DB, checks file/directory existence, and probes
    LanceDB table availability. Returns in ~1 second instead of 30-60s.
    """
    from jarvis.app.bootstrap import init_database
    from jarvis.app.config import JarvisConfig
    from jarvis.retrieval.vector_index import VectorIndex

    kb_path = resolve_knowledge_base_path()
    data_dir = Path.cwd() / ".jarvis-menubar"
    config = JarvisConfig(
        data_dir=data_dir,
        watched_folders=[kb_path] if kb_path.exists() else [],
    )

    checks: dict[str, bool] = {}
    details: dict[str, str] = {}
    failed_checks: list[str] = []

    # Database check
    db = None
    chunk_count = 0
    try:
        db = init_database(config)
        db.execute("SELECT 1")
        checks["database"] = True
        details["database"] = "OK"
        row = db.execute("SELECT COUNT(*) FROM chunks").fetchone()
        chunk_count = row[0] if row else 0
    except Exception as exc:
        checks["database"] = False
        details["database"] = str(exc)
        failed_checks.append("database")

    # Metrics (always OK for lightweight check)
    checks["metrics"] = True
    details["metrics"] = "OK"

    # Knowledge base
    kb_exists = kb_path.exists()
    checks["knowledge_base"] = kb_exists
    details["knowledge_base"] = str(kb_path) if kb_exists else "not configured"
    if not kb_exists:
        failed_checks.append("knowledge_base")

    # Watched folders
    checks["watched_folders"] = kb_exists
    details["watched_folders"] = "OK" if kb_exists else "no folders configured"

    # Export dir
    checks["export_dir"] = False
    details["export_dir"] = "not configured"

    # Vector search (just check if LanceDB is importable and table exists)
    try:
        vi = VectorIndex(db_path=data_dir / "vectors.lance")
        vector_available = vi._check_available()
        table = vi._get_table() if vector_available else None
        checks["vector_search"] = vector_available
        checks["vector_db"] = table is not None
        details["vector_search"] = "active" if vector_available else "FTS-only mode"
        details["vector_db"] = "OK" if table is not None else "table not initialized"
        if not vector_available:
            failed_checks.append("vector_search")
    except Exception:
        checks["vector_search"] = False
        checks["vector_db"] = False
        details["vector_search"] = "unavailable"
        details["vector_db"] = "unavailable"
        failed_checks.append("vector_search")

    # LLM model — probe without loading
    checks["model"] = False
    details["model"] = "not checked (lightweight mode)"

    # Embeddings / reranker — probe dependency availability without loading
    try:
        from jarvis.runtime.embedding_runtime import EmbeddingRuntime

        emb = EmbeddingRuntime()
        embedding_available = emb._check_available()
        checks["embeddings"] = embedding_available
        details["embeddings"] = (
            f"ready ({chunk_count} chunks indexed)" if embedding_available else "disabled (sentence-transformers unavailable)"
        )
    except Exception:
        checks["embeddings"] = False
        details["embeddings"] = "disabled (embedding probe failed)"

    try:
        from jarvis.retrieval.reranker import Reranker

        reranker = Reranker()
        reranker_available = reranker._check_available()
        checks["reranker"] = reranker_available
        details["reranker"] = "ready (lazy-loaded)" if reranker_available else "disabled (cross-encoder unavailable)"
    except Exception:
        checks["reranker"] = False
        details["reranker"] = "disabled (reranker probe failed)"

    # Governor — lightweight, skip
    checks["governor"] = True
    details["governor"] = "OK (not sampled)"

    # File watcher — not running in one-shot mode
    checks["file_watcher"] = False
    details["file_watcher"] = "not running (one-shot mode)"

    if db is not None:
        db.close()

    healthy = len(failed_checks) == 0
    return {
        "healthy": healthy,
        "message": "OK" if healthy else f"Issues: {', '.join(failed_checks)}",
        "checks": checks,
        "details": details,
        "failed_checks": failed_checks,
        "status_level": "healthy" if not failed_checks else ("warning" if len(failed_checks) <= 2 else "degraded"),
        "chunk_count": chunk_count,
        "knowledge_base_path": str(kb_path) if kb_exists else "",
        "bridge_mode": "one-shot",
    }


def _execute_command(command: str, payload: dict[str, object]) -> MenuBarCommandEnvelope:
    if command == "ask":
        return MenuBarCommandEnvelope(
            kind="query_result",
            query_result=_run_query(
                query=str(payload["query"]),
                model_id=str(payload.get("model", "qwen3.5:9b")),
            ),
        )
    if command == "record-once":
        return MenuBarCommandEnvelope(
            kind="query_result",
            query_result=_record_once(
                model_id=str(payload.get("model", "qwen3.5:9b")),
                device=str(payload["device"]) if payload.get("device") else None,
            ),
        )
    if command == "transcribe-once":
        return MenuBarCommandEnvelope(
            kind="transcription_result",
            transcription_result=_transcribe_once(
                model_id=str(payload.get("model", "qwen3.5:9b")),
                device=str(payload["device"]) if payload.get("device") else None,
            ),
        )
    if command == "transcribe-file":
        return MenuBarCommandEnvelope(
            kind="transcription_result",
            transcription_result=_transcribe_file(
                audio_path=str(payload["audio"]),
            ),
        )
    if command == "navigation-window":
        return MenuBarCommandEnvelope(
            kind="navigation_result",
            navigation_result=_build_navigation_window(
                query=str(payload["query"]),
                model_id=str(payload.get("model", "qwen3.5:9b")),
            ),
        )
    if command == "normalize-query":
        return MenuBarCommandEnvelope(
            kind="normalization_result",
            normalization_result=_normalize_query(
                query=str(payload["query"]),
            ),
        )
    if command == "synthesize-speech":
        return MenuBarCommandEnvelope(
            kind="speech_result",
            speech_result=_synthesize_speech(
                text=str(payload["text"]),
            ),
        )
    if command == "export-draft":
        return MenuBarCommandEnvelope(
            kind="export_result",
            export_result=_export_draft(
                content=str(payload["content"]),
                destination=Path(str(payload["destination"])).expanduser(),
                approved=bool(payload.get("approved", False)),
            ),
        )
    if command == "health":
        return MenuBarCommandEnvelope(
            kind="health_result",
            health_result=_health_light(),
        )
    return MenuBarCommandEnvelope(kind="error", error=f"Unknown command: {command}")


def _run_server(model_id: str) -> int:
    context = _build_context(model_id=model_id)
    try:
        print(json.dumps({"kind": "ready"}), flush=True)
        for raw_line in sys.stdin:
            line = raw_line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
                command = str(payload.get("command", ""))
                if command == "shutdown":
                    print(json.dumps({"kind": "shutdown"}), flush=True)
                    return 0
                if command == "ask":
                    stream_mode = bool(payload.get("stream", False))
                    if stream_mode and hasattr(context.orchestrator, "handle_turn_stream"):
                        turn = None
                        for item in context.orchestrator.handle_turn_stream(str(payload["query"])):
                            if isinstance(item, str):
                                print(json.dumps({"kind": "stream_chunk", "token": item}, ensure_ascii=False), flush=True)
                            else:
                                turn = item
                        envelope = MenuBarCommandEnvelope(
                            kind="stream_done",
                            query_result=_response_from_context(context=context, turn=turn) if turn else None,
                        )
                    else:
                        envelope = MenuBarCommandEnvelope(
                            kind="query_result",
                            query_result=_response_from_context(
                                context=context,
                                turn=context.orchestrator.handle_turn(str(payload["query"])),
                            ),
                        )
                elif command == "record-once":
                    stream_mode = bool(payload.get("stream", False))
                    device = str(payload["device"]) if payload.get("device") else None
                    if stream_mode and hasattr(context.orchestrator, "handle_turn_stream"):
                        turn = _record_once_stream_in_context(context=context, device=device)
                        envelope = MenuBarCommandEnvelope(
                            kind="stream_done",
                            query_result=_response_from_context(context=context, turn=turn) if turn else None,
                        )
                    else:
                        envelope = MenuBarCommandEnvelope(
                            kind="query_result",
                            query_result=_record_once_in_context(
                                context=context,
                                device=device,
                            ),
                        )
                elif command == "transcribe-once":
                    envelope = MenuBarCommandEnvelope(
                        kind="transcription_result",
                        transcription_result=_transcribe_once_in_context(
                            context=context,
                            device=str(payload["device"]) if payload.get("device") else None,
                        ),
                    )
                elif command == "transcribe-file":
                    envelope = MenuBarCommandEnvelope(
                        kind="transcription_result",
                        transcription_result=_transcribe_file(
                            audio_path=str(payload["audio"]),
                        ),
                    )
                elif command == "navigation-window":
                    envelope = MenuBarCommandEnvelope(
                        kind="navigation_result",
                        navigation_result=_build_navigation_window(
                            query=str(payload["query"]),
                            model_id=str(payload.get("model", model_id)),
                        ),
                    )
                elif command == "normalize-query":
                    envelope = MenuBarCommandEnvelope(
                        kind="normalization_result",
                        normalization_result=_normalize_query(
                            query=str(payload["query"]),
                        ),
                    )
                elif command == "synthesize-speech":
                    envelope = MenuBarCommandEnvelope(
                        kind="speech_result",
                        speech_result=_synthesize_speech(
                            text=str(payload["text"]),
                        ),
                    )
                elif command == "export-draft":
                    envelope = MenuBarCommandEnvelope(
                        kind="export_result",
                        export_result=_export_draft(
                            content=str(payload["content"]),
                            destination=Path(str(payload["destination"])).expanduser(),
                            approved=bool(payload.get("approved", False)),
                        ),
                    )
                elif command == "wake-listen-start":
                    # Start wake word detection — Swift sends audio chunks via wake-audio
                    try:
                        from openwakeword.model import Model as OWWModel
                        if not hasattr(context, "_oww_model"):
                            context._oww_model = OWWModel(
                                wakeword_models=["hey_jarvis_v0.1"],
                                inference_framework="onnx",
                            )
                        envelope = MenuBarCommandEnvelope(kind="wake_ready")
                    except Exception as exc:
                        envelope = MenuBarCommandEnvelope(
                            kind="error", error=f"Wake word init failed: {exc}",
                        )
                elif command == "wake-audio":
                    # Process an audio chunk for wake word detection
                    # Expects: {"command": "wake-audio", "pcm_b64": "base64-encoded-16kHz-int16"}
                    import base64
                    import numpy as np
                    pcm_b64 = str(payload.get("pcm_b64", ""))
                    pcm_bytes = base64.b64decode(pcm_b64)
                    pcm_array = np.frombuffer(pcm_bytes, dtype=np.int16)
                    oww = getattr(context, "_oww_model", None)
                    detected = False
                    score = 0.0
                    if oww is not None and len(pcm_array) > 0:
                        oww.predict(pcm_array)
                        for model_name in oww.prediction_buffer:
                            scores = oww.prediction_buffer[model_name]
                            if scores and scores[-1] >= 0.2:
                                detected = True
                                score = scores[-1]
                                oww.reset()
                                break
                    if detected:
                        envelope = MenuBarCommandEnvelope(kind="wake_detected")
                        # Also include score in a simple way
                        print(json.dumps({"kind": "wake_detected", "score": round(score, 3)}, ensure_ascii=False), flush=True)
                        continue
                    else:
                        continue  # No output for non-detection (keep it fast)
                elif command == "wake-listen-stop":
                    if hasattr(context, "_oww_model"):
                        context._oww_model.reset()
                    envelope = MenuBarCommandEnvelope(kind="wake_stopped")
                elif command == "health":
                    envelope = MenuBarCommandEnvelope(
                        kind="health_result",
                        health_result=_health_payload(context=context),
                    )
                else:
                    envelope = MenuBarCommandEnvelope(
                        kind="error",
                        error=f"Unknown command: {command}",
                    )
            except Exception as exc:
                traceback.print_exc(file=sys.stderr)
                envelope = MenuBarCommandEnvelope(kind="error", error=str(exc))
            print(json.dumps(asdict(envelope), ensure_ascii=False), flush=True)
        return 0
    finally:
        shutdown_runtime_context(context)


def main(argv: list[str] | None = None) -> int:
    """Run a one-shot JSON query suitable for the SwiftUI menu bar shell."""
    configure_logging(level=logging.WARNING, json_logs=False)

    parser = argparse.ArgumentParser(description="JARVIS menu bar bridge")
    subparsers = parser.add_subparsers(dest="command", required=True)

    ask_parser = subparsers.add_parser("ask", help="Run a text query")
    ask_parser.add_argument("--query", required=True, help="User query to send to JARVIS")
    ask_parser.add_argument("--model", default="qwen3.5:9b", help="Override default model")

    record_parser = subparsers.add_parser("record-once", help="Record one microphone query")
    record_parser.add_argument("--model", default="qwen3.5:9b", help="Override default model")
    record_parser.add_argument("--device", help="Optional microphone input device name")
    transcribe_parser = subparsers.add_parser("transcribe-once", help="Record one microphone query and return transcript only")
    transcribe_parser.add_argument("--model", default="qwen3.5:9b", help="Override default model")
    transcribe_parser.add_argument("--device", help="Optional microphone input device name")

    transcribe_file_parser = subparsers.add_parser("transcribe-file", help="Transcribe a pre-recorded audio file")
    transcribe_file_parser.add_argument("--audio", required=True, help="Path to WAV audio file")
    navigation_parser = subparsers.add_parser("navigation-window", help="Return exploration candidates for a query")
    navigation_parser.add_argument("--query", required=True, help="Query to analyze for navigation assistance")
    navigation_parser.add_argument("--model", default="qwen3.5:9b", help="Override default model")
    normalize_parser = subparsers.add_parser("normalize-query", help="Normalize a spoken code query")
    normalize_parser.add_argument("--query", required=True, help="Query to normalize")

    export_parser = subparsers.add_parser("export-draft", help="Export the current draft")
    export_parser.add_argument("--content", required=True, help="Draft content to export")
    export_parser.add_argument("--destination", required=True, help="Export destination path")
    export_parser.add_argument(
        "--approved",
        action="store_true",
        help="Approval already granted in the menu bar UI",
    )
    health_parser = subparsers.add_parser("health", help="Return menu bar startup health")
    health_parser.add_argument("--model", default="qwen3.5:9b", help="Override default model")
    server_parser = subparsers.add_parser("server", help="Run persistent stdin/stdout JSON bridge")
    server_parser.add_argument("--model", default="qwen3.5:9b", help="Override default model")
    args = parser.parse_args(argv)

    if args.command == "server":
        return _run_server(args.model)

    try:
        if args.command == "ask":
            envelope = _execute_command(
                "ask",
                {"query": args.query, "model": args.model},
            )
        elif args.command == "record-once":
            envelope = _execute_command(
                "record-once",
                {"model": args.model, "device": args.device},
            )
        elif args.command == "transcribe-once":
            envelope = _execute_command(
                "transcribe-once",
                {"model": args.model, "device": args.device},
            )
        elif args.command == "transcribe-file":
            envelope = _execute_command(
                "transcribe-file",
                {"audio": args.audio},
            )
        elif args.command == "navigation-window":
            envelope = _execute_command(
                "navigation-window",
                {"query": args.query, "model": args.model},
            )
        elif args.command == "normalize-query":
            envelope = _execute_command(
                "normalize-query",
                {"query": args.query},
            )
        elif args.command == "health":
            envelope = _execute_command(
                "health",
                {"model": args.model},
            )
        else:
            envelope = _execute_command(
                "export-draft",
                {
                    "content": args.content,
                    "destination": args.destination,
                    "approved": bool(args.approved),
                },
            )
    except Exception as exc:
        envelope = MenuBarCommandEnvelope(kind="error", error=str(exc))

    print(json.dumps(asdict(envelope), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
