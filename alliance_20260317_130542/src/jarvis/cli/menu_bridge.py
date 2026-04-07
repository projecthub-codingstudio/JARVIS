"""JSON bridge between the Python core and the macOS menu bar app."""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import re
import sys
import tempfile
import time
import threading
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
from jarvis.core.action_resolver import execute_action, parse_action_target
from jarvis.core.intent_policy import resolve_menu_intent_policy
from jarvis.identifier_restoration import build_identifier_lexicon, score_identifier_candidates
from jarvis.query_normalization import normalize_spoken_code_query
from jarvis.runtime_paths import resolve_menubar_data_dir

from jarvis.runtime.audio_recorder import AudioRecorder
from jarvis.runtime.mlx_runtime import build_stub_spoken_response
from jarvis.observability.health import check_health
from jarvis.observability.logging import configure_logging
from jarvis.runtime.stt_biasing import build_vocabulary_hint
from jarvis.runtime.stt_runtime import WhisperCppSTT
from jarvis.runtime.tts_runtime import LocalTTSRuntime
from jarvis.tools.draft_export import DraftExportTool

_MAX_QUOTE_CHARS = 160
_TTS_DIR = Path(tempfile.gettempdir()) / "jarvis_tts"
_TTS_WARMUP_SAMPLE_TEXT = "준비 완료."
_TTS_INFLIGHT_LOCK = threading.Lock()
_TTS_INFLIGHT: dict[str, threading.Event] = {}
_TTS_CACHE_VERSION = "v5"
_MAX_TEXT_PREVIEW_LINES = 30
_MAX_TEXT_PREVIEW_CHARS = 300
_MAX_CODE_PREVIEW_LINES = 50
_MAX_CODE_PREVIEW_CHARS = 300


def _tts_backend() -> str:
    configured = __import__("os").getenv("JARVIS_TTS_BACKEND", "say").strip().lower()
    if configured in {"auto", "qwen3", "say"}:
        return configured
    return "say"


def _tts_cache_key(text: str) -> str:
    env = __import__("os").environ
    resolved_tail_pad_ms = env.get("JARVIS_TTS_TAIL_PAD_MS", "").strip() or "220"
    resolved_en_speaker = env.get("JARVIS_QWEN_TTS_SPEAKER_EN", "").strip() or "Ryan"
    resolved_ko_speaker = env.get("JARVIS_QWEN_TTS_SPEAKER_KO", "").strip() or "Ryan"
    resolved_instruct = env.get("JARVIS_QWEN_TTS_INSTRUCT", "").strip() or (
        "Speak like a calm, polished, male AI assistant with a subtle British-leaning tone. "
        "Low-medium pitch, measured pacing, precise diction, understated wit, "
        "never bubbly, never cartoonish, never exaggerated."
    )
    resolved_shared_voice = env.get("JARVIS_QWEN_TTS_SHARED_VOICE", "").strip() or "1"
    resolved_clone_mode = env.get("JARVIS_QWEN_TTS_CLONE_MODE", "").strip() or "xvector"
    resolved_ref_text_en = env.get("JARVIS_QWEN_TTS_REF_TEXT_EN", "").strip() or env.get("JARVIS_QWEN_TTS_REF_TEXT", "").strip() or (
        "Good evening. All systems are stable and ready for your command."
    )
    resolved_ref_text_ko = env.get("JARVIS_QWEN_TTS_REF_TEXT_KO", "").strip() or env.get("JARVIS_QWEN_TTS_REF_TEXT", "").strip() or (
        "안녕하세요. 모든 시스템이 안정적으로 작동 중이며 명령을 기다리고 있습니다."
    )
    signature = "|".join(
        [
            _TTS_CACHE_VERSION,
            _tts_backend(),
            env.get("JARVIS_TTS_VOICE", ""),
            resolved_en_speaker,
            resolved_ko_speaker,
            resolved_instruct,
            resolved_shared_voice,
            resolved_clone_mode,
            resolved_ref_text_en,
            resolved_ref_text_ko,
            resolved_tail_pad_ms,
            text,
        ]
    )
    return hashlib.sha256(signature.encode("utf-8")).hexdigest()


def _tts_cache_path_for(text: str) -> Path:
    return _TTS_DIR / f"speech_cache_{_tts_cache_key(text)}.aiff"


def _claim_tts_generation(cache_path: Path) -> tuple[bool, threading.Event]:
    key = str(cache_path)
    with _TTS_INFLIGHT_LOCK:
        existing = _TTS_INFLIGHT.get(key)
        if existing is not None:
            return False, existing
        event = threading.Event()
        _TTS_INFLIGHT[key] = event
        return True, event


def _release_tts_generation(cache_path: Path, event: threading.Event) -> None:
    key = str(cache_path)
    with _TTS_INFLIGHT_LOCK:
        current = _TTS_INFLIGHT.get(key)
        if current is event:
            _TTS_INFLIGHT.pop(key, None)
    event.set()


def _detect_source_type(path: str) -> str:
    if path.startswith(("http://", "https://")):
        return "web"
    code_exts = {".py", ".ts", ".tsx", ".js", ".jsx", ".yaml", ".yml", ".json", ".sql"}
    suffix = Path(path).suffix.lower()
    return "code" if suffix in code_exts else "document"


def _quote_for(item: EvidenceItem) -> str:
    text = item.text.strip().replace("\n", " ")
    if len(text) > _MAX_QUOTE_CHARS:
        return text[:_MAX_QUOTE_CHARS] + "..."
    return text


def _heading_path_text(value: object) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, tuple):
        return " > ".join(str(part).strip() for part in value if str(part).strip())
    return ""


def _detect_source_presentation_kind(item: EvidenceItem, source_type: str) -> str:
    heading_path = _heading_path_text(item.heading_path).lower()
    if source_type == "web":
        return "web_page"
    if "table-row" in heading_path:
        return "table_row"
    if source_type == "code":
        return "code_symbol"
    return "document_section"


def _source_presentation_title(item: EvidenceItem, *, kind: str, heading_path: str) -> str:
    if kind == "table_row":
        match = re.search(r"\bDay\s*=\s*(\d+)", item.text, re.IGNORECASE)
        if match:
            return f"{match.group(1)}일차 표 항목"
        if heading_path:
            return heading_path.split(">")[-1].strip()
        return "표 항목"
    if kind == "code_symbol":
        if heading_path:
            return heading_path.split(">")[-1].strip()
        return Path(item.source_path or item.document_id).name
    if kind == "document_section":
        if heading_path:
            return heading_path.split(">")[-1].strip()
        return Path(item.source_path or item.document_id).name
    if kind == "web_page":
        if heading_path:
            return heading_path.split(">")[-1].strip()
        return Path(item.source_path or item.document_id).name
    return heading_path.split(">")[-1].strip() if heading_path else Path(item.source_path or item.document_id).name


def _parse_table_preview_lines(text: str) -> list[str]:
    pairs = re.findall(r"([A-Za-z][A-Za-z0-9_ ]+)=([^|]+)", text)
    if not pairs:
        return []
    labels = {
        "Day": "일차",
        "Breakfast": "아침",
        "Lunch": "점심",
        "Dinner": "저녁",
        "Snack": "간식",
        "Drinks": "음료",
        "Calories": "칼로리",
        "Supplements": "보충제",
        "Morning Supplements": "오전 보충제",
        "Evening Supplements": "저녁 보충제",
        "Pre-Workout": "운동 전",
        "Post-Workout": "운동 후",
    }
    lines: list[str] = []
    day_value = ""
    for key, value in pairs:
        normalized_key = key.strip()
        normalized_value = " ".join(value.split()).strip()
        if not normalized_value:
            continue
        if normalized_key == "Day":
            day_value = normalized_value
            continue
        label = labels.get(normalized_key, normalized_key)
        lines.append(f"{label}: {normalized_value}")
    if day_value:
        lines.insert(0, f"일차: {day_value}")
    return lines[:6]


def _wrap_preview_text(
    text: str,
    *,
    max_lines: int = _MAX_TEXT_PREVIEW_LINES,
    max_chars: int = _MAX_TEXT_PREVIEW_CHARS,
) -> list[str]:
    normalized = " ".join(text.split()).strip()
    if not normalized:
        return []

    lines: list[str] = []
    remaining = normalized
    while remaining and len(lines) < max_lines:
        if len(remaining) <= max_chars:
            lines.append(remaining)
            break
        split_at = remaining.rfind(" ", 0, max_chars + 1)
        if split_at < max_chars // 2:
            split_at = max_chars
        chunk = remaining[:split_at].rstrip(",;: ")
        remaining = remaining[split_at:].lstrip()
        if len(lines) == max_lines - 1 and remaining:
            lines.append(chunk + "...")
            break
        lines.append(chunk)
    return lines


def _parse_code_preview_lines(text: str) -> list[str]:
    lines: list[str] = []
    for raw_line in text.splitlines():
        cleaned = raw_line.rstrip()
        if not cleaned.strip():
            continue
        if len(cleaned) > _MAX_CODE_PREVIEW_CHARS:
            cleaned = cleaned[:_MAX_CODE_PREVIEW_CHARS].rstrip() + "..."
        lines.append(cleaned)
        if len(lines) >= _MAX_CODE_PREVIEW_LINES:
            break
    return lines


def _source_presentation_preview_lines(item: EvidenceItem, *, kind: str) -> list[str]:
    if kind == "table_row":
        return _parse_table_preview_lines(item.text)
    if kind == "code_symbol":
        return _parse_code_preview_lines(item.text)
    if kind in {"document_section", "web_page"}:
        return _wrap_preview_text(item.text)
    return []


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
    full_source_path: str
    source_type: str
    quote: str
    state: str
    relevance_score: float
    heading_path: str = ""


@dataclass(frozen=True)
class MenuBarSourcePresentation:
    kind: str
    source_path: str
    full_source_path: str
    source_type: str
    heading_path: str = ""
    quote: str = ""
    title: str = ""
    preview_lines: list[str] = field(default_factory=list)


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
class MenuBarGuideDirective:
    intent: str
    skill: str
    loop_stage: str
    clarification_prompt: str = ""
    missing_slots: list[str] = field(default_factory=list)
    suggested_replies: list[str] = field(default_factory=list)
    should_hold: bool = False


@dataclass(frozen=True)
class MenuBarResponse:
    query: str
    response: str
    has_evidence: bool
    spoken_response: str = ""
    citations: list[MenuBarCitation] = field(default_factory=list)
    status: MenuBarStatus | None = None
    render_hints: MenuBarRenderHints | None = None
    exploration: MenuBarExplorationState | None = None
    guide_directive: MenuBarGuideDirective | None = None
    full_response_path: str = ""
    source_presentation: MenuBarSourcePresentation | None = None


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
class MenuBarProgressResponse:
    message: str


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
    progress_result: MenuBarProgressResponse | None = None
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
    planner_analysis: object | None = None,
) -> MenuBarResponse:
    """Serialize a completed turn into a menu bar-friendly payload."""
    citations: list[MenuBarCitation] = []
    source_presentation: MenuBarSourcePresentation | None = None
    if answer is not None:
        # Evidence items already passed retrieval + reranking filters.
        # No additional threshold — reranker scores use a different scale.
        for item in answer.evidence.items[:5]:
            full_path = item.source_path or item.document_id
            display_name = Path(full_path).name if full_path else item.document_id
            citations.append(MenuBarCitation(
                label=item.citation.label,
                source_path=display_name,
                full_source_path=full_path,
                source_type=_detect_source_type(full_path),
                quote=_quote_for(item),
                state=item.citation.state.value,
                relevance_score=item.relevance_score,
                heading_path=_heading_path_text(item.heading_path),
            ))
        if answer.evidence.items:
            top_item = answer.evidence.items[0]
            top_full_path = top_item.source_path or top_item.document_id
            top_source_type = _detect_source_type(top_full_path)
            heading_path = _heading_path_text(top_item.heading_path)
            source_kind = _detect_source_presentation_kind(top_item, top_source_type)
            preview_lines = _source_presentation_preview_lines(top_item, kind=source_kind)
            source_presentation = MenuBarSourcePresentation(
                kind=source_kind,
                source_path=Path(top_full_path).name if top_full_path else top_item.document_id,
                full_source_path=top_full_path,
                source_type=top_source_type,
                heading_path=heading_path,
                quote=_quote_for(top_item),
                title=_source_presentation_title(top_item, kind=source_kind, heading_path=heading_path),
                preview_lines=preview_lines,
            )

    mode = _response_mode(turn, answer)

    full_text = turn.assistant_output
    full_response_path = ""
    display_text = full_text
    spoken_text = _build_spoken_response(turn=turn, answer=answer, display_text=display_text)

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
    exploration = (
        _build_cited_document_exploration_state(
            citations=citations,
            source_presentation=source_presentation,
            knowledge_base_path=knowledge_base_path,
        )
        if interaction_mode == "document_exploration" and citation_count > 0
        else None
    )
    if exploration is None:
        exploration = _build_exploration_state(
            query=turn.user_input,
            interaction_mode=interaction_mode,
            knowledge_base_path=knowledge_base_path,
        )
    guide_directive = _build_guide_directive(
        query=turn.user_input,
        response_text=full_text,
        interaction_mode=interaction_mode,
        exploration=exploration,
        planner_analysis=planner_analysis,
        has_evidence=turn.has_evidence,
    )

    return MenuBarResponse(
        query=turn.user_input,
        response=display_text,
        spoken_response=spoken_text,
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
        guide_directive=guide_directive,
        full_response_path=full_response_path,
        source_presentation=source_presentation,
    )


def _build_spoken_response(
    *,
    turn: ConversationTurn,
    answer: AnswerDraft | None,
    display_text: str,
) -> str:
    if answer is None:
        return display_text
    if answer.model_id == "stub":
        spoken = build_stub_spoken_response(turn.user_input, answer.evidence)
        if spoken:
            return spoken
    return answer.content or display_text


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


def _relative_exploration_path(full_path: str, knowledge_base_path: Path | None) -> str:
    if not full_path:
        return ""
    candidate = Path(full_path)
    if knowledge_base_path is not None:
        try:
            return candidate.resolve().relative_to(knowledge_base_path.resolve()).as_posix()
        except (OSError, RuntimeError, ValueError):
            pass
    return candidate.name or full_path


def _build_cited_document_exploration_state(
    *,
    citations: list[MenuBarCitation],
    source_presentation: MenuBarSourcePresentation | None,
    knowledge_base_path: Path | None,
) -> MenuBarExplorationState | None:
    document_citations = [
        citation for citation in citations
        if citation.source_type == "document" and citation.full_source_path
    ]
    if not document_citations:
        return None

    preview_by_path: dict[str, str] = {}
    if source_presentation is not None and source_presentation.full_source_path:
        preview_by_path[source_presentation.full_source_path] = "\n".join(
            line.strip() for line in source_presentation.preview_lines if line.strip()
        ).strip()

    ranked: list[MenuBarExplorationItem] = []
    seen_paths: set[str] = set()
    for citation in document_citations:
        full_path = citation.full_source_path
        if full_path in seen_paths:
            continue
        seen_paths.add(full_path)
        preview = preview_by_path.get(full_path) or citation.quote
        ranked.append(
            MenuBarExplorationItem(
                label=citation.source_path,
                kind="document",
                path=_relative_exploration_path(full_path, knowledge_base_path),
                score=round(citation.relevance_score, 3),
                preview=preview,
            )
        )

    if not ranked:
        return None

    return MenuBarExplorationState(
        mode="document_exploration",
        target_document=ranked[0].label,
        document_candidates=ranked[:4],
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


def _analysis_intent(planner_analysis: object | None, interaction_mode: str) -> str:
    intent = getattr(planner_analysis, "intent", "") if planner_analysis is not None else ""
    if intent:
        return str(intent)
    if interaction_mode == "source_exploration":
        return "source_navigation"
    if interaction_mode == "document_exploration":
        return "document_navigation"
    return "qa"


def _skill_for(interaction_mode: str, query: str) -> str:
    lowered = query.lower()
    if interaction_mode == "source_exploration":
        return "source_exploration"
    if interaction_mode == "document_exploration":
        return "document_review"
    if (
        "지하철" in lowered
        or "버스" in lowered
        or "경로" in lowered
        or "길찾기" in lowered
        or "가는 길" in lowered
        or "가는길" in lowered
    ):
        return "route_guidance"
    return "conversation_support"


def _extract_question_prompt(text: str) -> str:
    normalized = " ".join(segment.strip() for segment in text.splitlines() if segment.strip()).strip()
    if not normalized or "?" not in normalized:
        return ""
    parts = [segment.strip() for segment in normalized.split("?") if segment.strip()]
    if not parts:
        return ""
    for segment in reversed(parts):
        if any(token in segment for token in ("어디", "어느", "무엇", "말씀", "알려", "선택", "확인", "추가")):
            return f"{segment}?"
    return f"{parts[0]}?"


def _missing_slots_for(interaction_mode: str, exploration: MenuBarExplorationState | None) -> list[str]:
    if exploration is None:
        return []
    slots: list[str] = []
    if interaction_mode == "document_exploration":
        if not exploration.target_document:
            slots.append("target_document")
        if len(exploration.document_candidates) > 1:
            slots.append("document_selection")
    elif interaction_mode == "source_exploration":
        if not exploration.target_file:
            slots.append("target_file")
        scoped_count = len(exploration.file_candidates) + len(exploration.class_candidates) + len(exploration.function_candidates)
        if scoped_count > 1:
            slots.append("source_selection")
    return slots


def _suggested_replies_for(
    interaction_mode: str,
    exploration: MenuBarExplorationState | None,
) -> list[str]:
    if exploration is not None:
        labels = [
            *(item.label for item in exploration.document_candidates[:2]),
            *(item.label for item in exploration.file_candidates[:2]),
            *(item.label for item in exploration.class_candidates[:2]),
            *(item.label for item in exploration.function_candidates[:2]),
        ]
        deduped: list[str] = []
        for label in labels:
            cleaned = label.strip()
            if cleaned and cleaned not in deduped:
                deduped.append(cleaned)
        if deduped:
            return deduped
    if interaction_mode == "document_exploration":
        return ["첫 번째 문서", "문서 제목으로 지정", "이 문서 요약해줘"]
    if interaction_mode == "source_exploration":
        return ["첫 번째 후보", "파일 이름으로 지정", "이 클래스 설명해줘"]
    return ["현재 위치 추가", "대상 이름 추가", "조건을 더 구체화"]


def _clarification_prompt_for(
    *,
    interaction_mode: str,
    response_text: str,
    missing_slots: list[str],
) -> str:
    extracted = _extract_question_prompt(response_text)
    if extracted:
        return extracted
    if "target_document" in missing_slots or "document_selection" in missing_slots:
        return "어떤 문서를 기준으로 이어서 볼지 알려주세요."
    if "target_file" in missing_slots or "source_selection" in missing_slots:
        return "어느 파일, 클래스, 함수 기준으로 이어서 볼지 알려주세요."
    return ""


def _build_guide_directive(
    *,
    query: str,
    response_text: str,
    interaction_mode: str,
    exploration: MenuBarExplorationState | None,
    planner_analysis: object | None,
    has_evidence: bool,
) -> MenuBarGuideDirective:
    missing_slots = _missing_slots_for(interaction_mode, exploration) if not has_evidence else []
    clarification_prompt = _clarification_prompt_for(
        interaction_mode=interaction_mode,
        response_text=response_text,
        missing_slots=missing_slots,
    )
    should_hold = bool(clarification_prompt or missing_slots or response_text.strip())
    if clarification_prompt and (not has_evidence or _extract_question_prompt(response_text)):
        loop_stage = "waiting_user_reply"
    elif has_evidence:
        loop_stage = "presenting"
    else:
        loop_stage = "reasoning"
    return MenuBarGuideDirective(
        intent=_analysis_intent(planner_analysis, interaction_mode),
        skill=_skill_for(interaction_mode, query),
        loop_stage=loop_stage,
        clarification_prompt=clarification_prompt,
        missing_slots=missing_slots,
        suggested_replies=_suggested_replies_for(interaction_mode, exploration),
        should_hold=should_hold,
    )


def _build_context(*, model_id: str, reporter=None):
    return build_runtime_context(
        model_id=model_id,
        start_watcher_enabled=False,
        start_background_backfill=False,
        allow_mlx=model_id.strip().lower() != "stub",
        data_dir=resolve_menubar_data_dir(),
        reporter=reporter,
    )


def _resolve_bridge_knowledge_base_path() -> Path | None:
    path = resolve_knowledge_base_path(None)
    return path if path.exists() else None


def _response_from_context(*, context: object, turn: ConversationTurn) -> MenuBarResponse:
    answer = context.orchestrator.last_answer
    planner = getattr(context.orchestrator, "_planner", None)
    planner_analysis = None
    if planner is not None:
        try:
            planner_analysis = planner.analyze(turn.user_input)
        except Exception:
            logging.getLogger(__name__).debug("planner analyze failed for guide directive", exc_info=True)
    return build_menu_response(
        turn=turn,
        answer=answer,
        safe_mode=context.error_monitor.safe_mode_active(),
        degraded_mode=context.error_monitor.degraded_mode,
        generation_blocked=context.error_monitor.generation_blocked,
        write_blocked=context.error_monitor.write_blocked,
        rebuild_index_required=context.error_monitor.rebuild_index_required,
        knowledge_base_path=context.knowledge_base_path,
        planner_analysis=planner_analysis,
    )


def _normalize_bridge_query(query: str) -> str:
    normalized = normalize_spoken_code_query(
        query,
        knowledge_base_path=_resolve_bridge_knowledge_base_path(),
    ).strip()
    return normalized or query.strip()


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


def _intent_override_response(query: str, *, model_id: str) -> MenuBarResponse | None:
    del model_id
    resolution = resolve_menu_intent_policy(
        query,
        knowledge_base_path=_resolve_bridge_knowledge_base_path(),
    )
    if resolution.policy is None:
        return None

    # Action intent: parse and execute via ActionResolver
    if resolution.policy.intent == "action":
        target = parse_action_target(query)
        if target is None:
            return None  # fall through to RAG
        result = execute_action(target)
        loop_stage = "idle" if result.success else "error"
        return MenuBarResponse(
            query=query,
            response=result.display_response,
            spoken_response=result.spoken_response,
            has_evidence=False,
            citations=[],
            status=MenuBarStatus(
                mode="action_execute",
                safe_mode=False,
                degraded_mode=False,
                generation_blocked=False,
                write_blocked=False,
                rebuild_index_required=False,
            ),
            render_hints=MenuBarRenderHints(
                response_type="action_result",
                primary_source_type="none",
                source_profile="none",
                interaction_mode="action",
                citation_count=0,
                truncated=False,
            ),
            exploration=None,
            guide_directive=MenuBarGuideDirective(
                intent="action",
                skill="action_resolver",
                loop_stage=loop_stage,
                should_hold=False,
            ),
            full_response_path="",
        )

    policy = resolution.policy
    return MenuBarResponse(
        query=query,
        response=policy.response_text,
        spoken_response=policy.response_text,
        has_evidence=False,
        citations=[],
        status=MenuBarStatus(
            mode=policy.mode,
            safe_mode=False,
            degraded_mode=False,
            generation_blocked=False,
            write_blocked=False,
            rebuild_index_required=False,
        ),
        render_hints=MenuBarRenderHints(
            response_type=policy.response_type,
            primary_source_type=policy.primary_source_type,
            source_profile=policy.source_profile,
            interaction_mode=policy.interaction_mode,
            citation_count=0,
            truncated=False,
        ),
        exploration=None,
        guide_directive=MenuBarGuideDirective(
            intent=policy.intent,
            skill=policy.skill,
            loop_stage="presenting",
            clarification_prompt="",
            missing_slots=[],
            suggested_replies=list(policy.suggested_replies),
            should_hold=True,
        ),
        full_response_path="",
    )


def _run_query(*, query: str, model_id: str) -> MenuBarResponse:
    normalized_query = _normalize_bridge_query(query)
    if override := _intent_override_response(normalized_query, model_id=model_id):
        return override
    context = _build_context(model_id=model_id)
    try:
        return _run_query_in_context(
            query=query,
            model_id=model_id,
            context=context,
        )
    finally:
        shutdown_runtime_context(context)


def _run_query_in_context(*, query: str, model_id: str, context: object, session_id: str = "") -> MenuBarResponse:
    normalized_query = _normalize_bridge_query(query)
    if override := _intent_override_response(normalized_query, model_id=model_id):
        return override
    turn = context.orchestrator.handle_turn(normalized_query, session_id=session_id)
    turn.user_input = query
    return _response_from_context(context=context, turn=turn)


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
            backend=_tts_backend(),
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
        backend=_tts_backend(),
    )
    _TTS_DIR.mkdir(parents=True, exist_ok=True)
    cache_path = _tts_cache_path_for(clean_text)
    if cache_path.exists() and cache_path.stat().st_size > 0:
        return MenuBarSpeechResponse(audio_path=str(cache_path))

    owner, event = _claim_tts_generation(cache_path)
    if not owner:
        event.wait(timeout=180)
        if cache_path.exists() and cache_path.stat().st_size > 0:
            return MenuBarSpeechResponse(audio_path=str(cache_path))
        owner, event = _claim_tts_generation(cache_path)
        if not owner:
            event.wait(timeout=30)
            if cache_path.exists() and cache_path.stat().st_size > 0:
                return MenuBarSpeechResponse(audio_path=str(cache_path))
            raise RuntimeError("기존 TTS 생성이 끝나지 않았습니다.")

    try:
        temp_output_path = _TTS_DIR / f"speech_{int(time.time() * 1000)}.aiff"
        result = tts_runtime.synthesize(clean_text, temp_output_path)
        if result != cache_path:
            result.replace(cache_path)
        return MenuBarSpeechResponse(audio_path=str(cache_path))
    finally:
        _release_tts_generation(cache_path, event)


def _warmup_tts() -> bool:
    tts_runtime = LocalTTSRuntime(
        voice=__import__("os").getenv("JARVIS_TTS_VOICE"),
        backend=_tts_backend(),
    )
    warmed = tts_runtime.warmup()
    if not warmed:
        return False
    if _tts_backend() == "say":
        return True
    try:
        _TTS_DIR.mkdir(parents=True, exist_ok=True)
        cache_path = _tts_cache_path_for(_TTS_WARMUP_SAMPLE_TEXT)
        if not cache_path.exists() or cache_path.stat().st_size <= 0:
            tts_runtime.synthesize(_TTS_WARMUP_SAMPLE_TEXT, cache_path)
    except Exception:
        logging.getLogger(__name__).debug("full TTS warmup probe failed", exc_info=True)
    return True


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
        backend=_tts_backend(),
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
    failed_doc_count = 0
    try:
        failed_doc_query = context.bootstrap_result.db.execute(
            "SELECT COUNT(*) FROM documents WHERE indexing_status = 'FAILED'"
        )
        if hasattr(failed_doc_query, "fetchone"):
            failed_doc_row = failed_doc_query.fetchone()
            failed_doc_count = int(failed_doc_row[0]) if failed_doc_row else 0
    except Exception:
        failed_doc_count = 0
    details["index_failures"] = str(failed_doc_count)
    vector_available = context.vector_index._check_available()
    checks["vector_search"] = vector_available
    details["vector_search"] = "active" if vector_available else "FTS-only mode"

    failed_checks = list(status.failed_checks)
    if not checks["knowledge_base"]:
        failed_checks.append("knowledge_base")
    if not checks["vector_search"]:
        failed_checks.append("vector_search")
    if failed_doc_count > 0:
        failed_checks.append("index_failures")
    return {
        "healthy": status.healthy,
        "message": status.message,
        "checks": checks,
        "details": details,
        "failed_checks": failed_checks,
        "status_level": "healthy" if not failed_checks else ("warning" if len(failed_checks) <= 2 else "degraded"),
        "chunk_count": context.chunk_count,
        "knowledge_base_path": context.knowledge_base_path.name if context.knowledge_base_path else "not configured",
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
    data_dir = resolve_menubar_data_dir()
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
    doc_count = 0
    failed_doc_count = 0
    total_size_bytes = 0
    embedding_count = 0
    try:
        db = init_database(config)
        db.execute("SELECT 1")
        checks["database"] = True
        details["database"] = "OK"
        row = db.execute("SELECT COUNT(*) FROM chunks").fetchone()
        chunk_count = row[0] if row else 0
        doc_row = db.execute("SELECT COUNT(*) FROM documents WHERE indexing_status = 'INDEXED'").fetchone()
        doc_count = doc_row[0] if doc_row else 0
        failed_row = db.execute("SELECT COUNT(*) FROM documents WHERE indexing_status = 'FAILED'").fetchone()
        failed_doc_count = failed_row[0] if failed_row else 0
        size_row = db.execute("SELECT COALESCE(SUM(size_bytes), 0) FROM documents WHERE indexing_status = 'INDEXED'").fetchone()
        total_size_bytes = size_row[0] if size_row else 0
        emb_row = db.execute("SELECT COUNT(*) FROM chunks WHERE embedding_ref IS NOT NULL").fetchone()
        embedding_count = emb_row[0] if emb_row else 0
        failed_paths_rows = db.execute("SELECT path FROM documents WHERE indexing_status = 'FAILED' ORDER BY path").fetchall()
        failed_paths = [r[0] for r in failed_paths_rows]
    except Exception as exc:
        failed_paths = []
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
    details["index_failures"] = str(failed_doc_count)
    if not kb_exists:
        failed_checks.append("knowledge_base")
    if failed_doc_count > 0:
        failed_checks.append("index_failures")

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
        "doc_count": doc_count,
        "failed_doc_count": failed_doc_count,
        "failed_doc_paths": failed_paths,
        "total_size_bytes": total_size_bytes,
        "embedding_count": embedding_count,
        "knowledge_base_path": kb_path.name if kb_exists else "not configured",
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
    def _report_progress(message: str) -> None:
        print(json.dumps({
            "kind": "progress",
            "progress_result": {"message": message},
        }, ensure_ascii=False), flush=True)

    context = _build_context(model_id=model_id, reporter=_report_progress)
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
                        from jarvis.runtime.wake_word import (
                            resolve_wakeword_models,
                            resolve_wakeword_threshold,
                        )
                        if not hasattr(context, "_oww_model"):
                            context._oww_model = OWWModel(
                                wakeword_models=resolve_wakeword_models(),
                                inference_framework="onnx",
                            )
                        context._oww_threshold = resolve_wakeword_threshold()
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
                    threshold = float(getattr(context, "_oww_threshold", 0.2))
                    detected = False
                    score = 0.0
                    if oww is not None and len(pcm_array) > 0:
                        oww.predict(pcm_array)
                        for model_name in oww.prediction_buffer:
                            scores = oww.prediction_buffer[model_name]
                            if scores and scores[-1] >= threshold:
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
                        envelope = MenuBarCommandEnvelope(kind="wake_idle")
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
