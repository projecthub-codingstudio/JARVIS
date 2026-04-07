"""Application service entrypoints shared by all frontends."""

from __future__ import annotations

import atexit
from dataclasses import asdict
from datetime import datetime, timedelta
import html
from pathlib import Path
import json
import os
import re
import shlex
import subprocess
import sys
import threading
import time

from jarvis.cli.menu_bridge import (
    _build_context,
    build_menu_response,
    _build_navigation_window,
    _export_draft,
    _health_light,
    _normalize_query,
    _run_query_in_context,
    _synthesize_speech,
    _tts_backend,
    _transcribe_file,
    _warmup_tts,
)
from jarvis.app.runtime_context import resolve_knowledge_base_path, shutdown_runtime_context
from jarvis.contracts import (
    AnswerDraft,
    CitationRecord,
    CitationState,
    ConversationTurn,
    EvidenceItem,
    TypedQueryFragment,
    VerifiedEvidenceSet,
)
from jarvis.core.action_resolver import ActionTarget, execute_action
from jarvis.indexing.parsers import DocumentParser
from jarvis.service import builtin_capabilities as builtin_capabilities_module
from jarvis.service.builtin_capabilities import resolve_builtin_capability
from jarvis.service.intent_skill_registry import load_intent_skill_registry
from jarvis.service.intent_skill_store import (
    build_action_map_execution_plan,
    record_unmapped_request,
)
from jarvis.service.protocol import RpcRequest, RpcResponse, error_response, ok_response
from jarvis.spoken_response_prefetch import predict_prefetchable_spoken_response
from jarvis.transcript_repair import build_transcript_repair

_DEFAULT_MENU_BAR_MODEL_CHAIN = ("qwen3.5:9b", "stub")
_DEFAULT_MENU_BRIDGE_ASK_TIMEOUT_SECONDS = 50
_DEFAULT_MENU_BRIDGE_STUB_TIMEOUT_SECONDS = 18
_tts_warmup_lock = threading.Lock()
_tts_warmup_running = False
_tts_warmup_ready = False
_runtime_context_lock = threading.Lock()
_runtime_contexts: dict[str, object] = {}
_last_runtime_context_key: str | None = None
_ask_execution_lock = threading.Lock()
_session_document_state_lock = threading.Lock()
_session_document_state: dict[str, dict[str, object]] = {}
_document_parser = DocumentParser()
_installed_ollama_models_lock = threading.Lock()
_installed_ollama_models_cache: tuple[str, ...] = ()
_installed_ollama_models_cached_at = 0.0
_DOCUMENT_EXTENSIONS = {
    ".md",
    ".txt",
    ".pdf",
    ".docx",
    ".pptx",
    ".xlsx",
    ".csv",
    ".tsv",
    ".hwp",
    ".hwpx",
    ".html",
    ".htm",
}
_TOPIC_SOURCE_EXTENSIONS = _DOCUMENT_EXTENSIONS | {
    ".py",
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".swift",
    ".java",
    ".kt",
    ".go",
    ".rs",
    ".c",
    ".cc",
    ".cpp",
    ".h",
    ".hpp",
}

_PREFERRED_LOCAL_MODELS = (
    "qwen3.5:9b",
    "qwen3:14b",
    "qwen3:30b",
    "exaone3.5:7.8b",
    "llama3.2:latest",
    "deepseek-coder-v2:16b",
)

_CALENDAR_DEICTIC_DATE_RE = re.compile(
    r"(그날|그때|그\s*날짜|해당\s*날짜|that\s+day|that\s+date)",
    re.IGNORECASE,
)
_CALENDAR_TITLE_STRIP_RE = re.compile(
    r"((?:일정|캘린더|calendar|schedule|meeting|event|예약|회의)(?:을|를|에)?\s*(?:잡아줘|잡아|잡기|잡|생성해줘|생성|만들어줘|만들|추가해줘|추가|등록해줘|등록)|(?:create|add|schedule|book)\s+(?:a\s+)?(?:meeting|event|calendar)|부탁해줘|부탁해|해줘|해주세요|등록\s*부탁)",
    re.IGNORECASE,
)
_CALENDAR_ABSOLUTE_DATE_RE = re.compile(
    r"(?:(?P<year>\d{4})\s*년\s*)?(?P<month>\d{1,2})\s*월\s*(?P<day>\d{1,2})\s*일|(?P<iso_year>\d{4})-(?P<iso_month>\d{1,2})-(?P<iso_day>\d{1,2})",
    re.IGNORECASE,
)
_CALENDAR_TIME_RE = re.compile(
    r"(?:(?P<meridiem>오전|오후)\s*)?(?P<hour>\d{1,2})\s*시(?:\s*(?P<minute>\d{1,2})\s*분?)?",
    re.IGNORECASE,
)
_CALENDAR_COLON_TIME_RE = re.compile(r"\b(?P<hour>\d{1,2}):(?P<minute>\d{2})\b")
_CALENDAR_DURATION_RE = re.compile(
    r"(?P<value>\d+)\s*(?P<unit>시간|분|hours?|hrs?|hr|minutes?|mins?|min)\b",
    re.IGNORECASE,
)
_CALENDAR_UPDATE_TARGET_RE = re.compile(
    r"(?:로|으로)\s*(?:수정해줘|수정|변경해줘|변경|옮겨줘|옮겨|미뤄줘|미뤄|연기해줘|update|move|reschedule)|(?:수정해줘|수정|변경해줘|변경|옮겨줘|옮겨|미뤄줘|미뤄|연기해줘|update|move|reschedule)$",
    re.IGNORECASE,
)
_CALENDAR_UPDATE_PREFIX_RE = re.compile(
    r"^(?:일정(?:에서)?\s*)?",
    re.IGNORECASE,
)
_CALENDAR_UPDATE_DELTA_RE = re.compile(
    r"(?:(?P<number>\d+)\s*일|(?P<word>하루|이틀|사흘|나흘|닷새|엿새|이레|일주일))\s*(?P<direction>후|뒤|전)",
    re.IGNORECASE,
)
_CALENDAR_GENERIC_TITLE_RE = re.compile(
    r"^(일정|회의|미팅|약속|캘린더|event|meeting|schedule)$",
    re.IGNORECASE,
)
_APPLE_SCRIPT_MONTH_NAMES = (
    "",
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)
_NAMED_DAY_DELTAS = {
    "하루": 1,
    "이틀": 2,
    "사흘": 3,
    "나흘": 4,
    "닷새": 5,
    "엿새": 6,
    "이레": 7,
    "일주일": 7,
}


def _should_record_unmapped_skill_request(
    *,
    query: str,
    response_payload: object,
) -> bool:
    normalized_query = " ".join(query.split()).strip()
    if not normalized_query or not isinstance(response_payload, dict):
        return False
    if str(response_payload.get("task_id", "")).strip():
        return False
    status = response_payload.get("status")
    if not isinstance(status, dict):
        return False
    if str(status.get("mode", "")).strip().lower() != "no_evidence":
        return False
    directive = response_payload.get("guide_directive")
    if not isinstance(directive, dict):
        directive = {}
    if directive.get("missing_slots"):
        return False
    intent_id = str(directive.get("intent", "")).strip()
    if intent_id and load_intent_skill_registry().get(intent_id) is not None:
        return False
    return True


def _record_unmapped_skill_request(
    *,
    query: str,
    session_id: str,
    response_payload: object,
) -> None:
    if not _should_record_unmapped_skill_request(query=query, response_payload=response_payload):
        return
    try:
        record_unmapped_request(
            query=query,
            session_id=session_id,
            response_payload=response_payload,
        )
    except Exception:
        pass


def _menu_bar_model_chain() -> tuple[str, ...]:
    raw = os.getenv("JARVIS_MENU_BAR_MODEL_CHAIN", "").strip()
    if not raw:
        installed = _installed_ollama_models()
        for preferred in _PREFERRED_LOCAL_MODELS:
            if preferred in installed:
                return (preferred, "stub")
        return _DEFAULT_MENU_BAR_MODEL_CHAIN
    models = tuple(part.strip() for part in raw.split(",") if part.strip())
    return models or _DEFAULT_MENU_BAR_MODEL_CHAIN


def _installed_ollama_models() -> tuple[str, ...]:
    global _installed_ollama_models_cache, _installed_ollama_models_cached_at
    now = time.monotonic()
    with _installed_ollama_models_lock:
        if _installed_ollama_models_cache and (now - _installed_ollama_models_cached_at) < 30.0:
            return _installed_ollama_models_cache
    try:
        completed = subprocess.run(
            ["ollama", "list"],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
    except Exception:
        return ()
    if completed.returncode != 0:
        return ()
    lines = [line.strip() for line in completed.stdout.splitlines() if line.strip()]
    models: list[str] = []
    for line in lines[1:]:
        parts = line.split()
        if not parts:
            continue
        models.append(parts[0].strip())
    resolved = tuple(models)
    with _installed_ollama_models_lock:
        _installed_ollama_models_cache = resolved
        _installed_ollama_models_cached_at = now
    return resolved


def _menu_bridge_timeout_seconds(command: str, *, model_id: str | None = None) -> int:
    raw = os.getenv("JARVIS_MENU_BRIDGE_TIMEOUT_SECONDS", "").strip()
    if raw.isdigit():
        return max(5, int(raw))
    if command == "ask":
        if (model_id or "").strip().lower() == "stub":
            return _DEFAULT_MENU_BRIDGE_STUB_TIMEOUT_SECONDS
        return _DEFAULT_MENU_BRIDGE_ASK_TIMEOUT_SECONDS
    return 15


def _run_menu_bridge_subprocess(*, command: str, args: list[str]) -> dict[str, object]:
    alliance_root = Path(__file__).resolve().parents[3]
    src_root = alliance_root / "src"
    env = dict(os.environ)
    resolved_model_id: str | None = None
    if command == "ask":
        for index, part in enumerate(args):
            if part == "--model" and index + 1 < len(args):
                resolved_model_id = args[index + 1]
                break
    python_path = env.get("PYTHONPATH", "").strip()
    if python_path:
        env["PYTHONPATH"] = f"{src_root}{os.pathsep}{python_path}"
    else:
        env["PYTHONPATH"] = str(src_root)

    export_segments = [
        f"export {key}={shlex.quote(value)}"
        for key, value in sorted(env.items())
        if isinstance(value, str)
    ]
    command_segments = [
        f"cd {shlex.quote(str(alliance_root))}",
        *export_segments,
        "exec " + " ".join(
            shlex.quote(part)
            for part in [sys.executable, "-u", "-m", "jarvis.cli.menu_bridge", command, *args]
        ),
    ]
    completed = subprocess.run(
        ["/bin/zsh", "-lc", "; ".join(command_segments)],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(alliance_root),
        timeout=_menu_bridge_timeout_seconds(command, model_id=resolved_model_id),
    )
    stdout = completed.stdout.strip()
    stderr = completed.stderr.strip()
    if completed.returncode != 0:
        if stderr:
            raise RuntimeError(
                f"menu_bridge {command} failed (status={completed.returncode}): {stderr}"
            )
        raise RuntimeError(
            f"menu_bridge {command} failed (status={completed.returncode}, empty stdout)"
        )
    if not stdout:
        raise RuntimeError(f"menu_bridge {command} returned empty stdout")
    try:
        envelope = json.loads(stdout.splitlines()[-1])
    except Exception as exc:
        raise RuntimeError(
            f"menu_bridge {command} returned invalid JSON: {stdout[:400]}"
        ) from exc
    if envelope.get("kind") == "error":
        raise RuntimeError(str(envelope.get("error") or f"menu_bridge {command} error"))
    return envelope


def _runtime_context_key(model_id: str) -> str:
    normalized = model_id.strip().lower()
    return normalized or "stub"


def _shutdown_runtime_contexts(contexts: list[object]) -> None:
    for context in contexts:
        try:
            shutdown_runtime_context(context)
        except Exception:
            pass


def _evict_runtime_context(model_id: str) -> None:
    key = _runtime_context_key(model_id)
    with _runtime_context_lock:
        context = _runtime_contexts.pop(key, None)
    if context is not None:
        _shutdown_runtime_contexts([context])


def _get_runtime_context(*, model_id: str) -> object:
    key = _runtime_context_key(model_id)
    with _runtime_context_lock:
        context = _runtime_contexts.get(key)
        if context is not None:
            return context
        context = _build_context(model_id=model_id)
        _runtime_contexts[key] = context
        return context


def _clear_runtime_context_cache() -> None:
    global _last_runtime_context_key
    with _runtime_context_lock:
        contexts = list(_runtime_contexts.values())
        _runtime_contexts.clear()
        _last_runtime_context_key = None
    _shutdown_runtime_contexts(contexts)


def _run_menu_bridge_query_in_process(*, query: str, model_id: str, session_id: str = "") -> dict[str, object]:
    context = _get_runtime_context(model_id=model_id)
    response = _run_query_in_context(
        query=query,
        model_id=model_id,
        context=context,
        session_id=session_id,
    )
    global _last_runtime_context_key
    with _runtime_context_lock:
        _last_runtime_context_key = _runtime_context_key(model_id)
    return {
        "kind": "query_result",
        "query_result": asdict(response),
    }


def _reset_runtime_context_cache_for_tests() -> None:
    _clear_runtime_context_cache()


atexit.register(_clear_runtime_context_cache)


def _response_requires_model_fallback(response_payload: object) -> bool:
    if not isinstance(response_payload, dict):
        return False
    status = response_payload.get("status")
    if not isinstance(status, dict):
        return False
    mode = str(status.get("mode", "")).strip().lower()
    if mode in {"degraded", "safe_mode", "resource_blocked"}:
        return True
    if bool(status.get("degraded_mode", False)):
        return True
    if bool(status.get("generation_blocked", False)):
        return True
    return False


def _run_menu_bridge_ask_with_fallback(*, query: str, session_id: str = "") -> dict[str, object]:
    last_error: Exception | None = None
    model_chain = _menu_bar_model_chain()
    for index, model_id in enumerate(model_chain):
        try:
            with _ask_execution_lock:
                envelope = _run_menu_bridge_query_in_process(
                    query=query,
                    model_id=model_id,
                    session_id=session_id,
                )
            response_payload = envelope.get("query_result")
            has_more_models = index < len(model_chain) - 1
            if (
                has_more_models
                and model_id.strip().lower() != "stub"
                and _response_requires_model_fallback(response_payload)
            ):
                last_error = RuntimeError(
                    f"menu_bridge ask returned degraded response for model {model_id}"
                )
                continue
            return envelope
        except Exception as exc:
            _evict_runtime_context(model_id)
            last_error = exc
    if last_error is not None:
        raise last_error
    raise RuntimeError("menu_bridge ask failed: no models configured")


def _payload_dict(response: object) -> dict[str, object]:
    if isinstance(response, dict):
        return response
    return asdict(response)


def _build_answer_payload(response: object) -> dict[str, object]:
    data = _payload_dict(response)
    spoken_text = str(data.get("spoken_response", "")).strip()
    display_text = str(data.get("response", ""))
    natural_text = spoken_text or display_text
    structured_payload = data.get("structured_payload")
    return {
        "text": natural_text,
        "spoken_text": natural_text,
        "has_evidence": bool(data.get("has_evidence", False)),
        "citation_count": len(data.get("citations", [])),
        "kind": str(data.get("answer_kind", "retrieval_result") or "retrieval_result"),
        "task_id": str(data.get("task_id", "")).strip() or None,
        "structured_payload": structured_payload if isinstance(structured_payload, dict) else None,
        "full_response_path": data.get("full_response_path"),
    }


def _builtin_status_payload() -> dict[str, object]:
    return {
        "mode": "builtin_capability",
        "safe_mode": False,
        "degraded_mode": False,
        "generation_blocked": False,
        "write_blocked": False,
        "rebuild_index_required": False,
    }


def _empty_exploration_state() -> dict[str, object]:
    return {
        "mode": "general_query",
        "target_file": "",
        "target_document": "",
        "file_candidates": [],
        "document_candidates": [],
        "class_candidates": [],
        "function_candidates": [],
    }


def _action_target_from_step(step: dict[str, object]) -> ActionTarget | None:
    launch_target = str(step.get("launch_target", "")).strip()
    if not launch_target:
        return None
    action_type = "open_url" if launch_target.lower().startswith(("http://", "https://")) else "open_app"
    label = (
        str(step.get("title", "")).strip()
        or str(step.get("skill_id", "")).strip()
        or launch_target
    )
    return ActionTarget(
        action_type=action_type,
        target=launch_target,
        label=label,
        confidence="high",
    )


def _blocked_step_message(step: dict[str, object]) -> str:
    reason = str(step.get("status_reason", "")).strip()
    if reason == "local_app_missing":
        app_name = str(step.get("local_app_name", "")).strip() or str(step.get("launch_target", "")).strip()
        return f"{app_name} 앱 확인이 필요합니다."
    if reason == "api_not_configured":
        provider = str(step.get("api_provider", "")).strip() or "API"
        return f"{provider} 설정이 아직 연결되지 않았습니다."
    if reason == "missing_launch_target":
        return "실행 대상이 비어 있습니다."
    return "추가 설정이 필요합니다."


def _build_action_map_execution_response(query: str) -> dict[str, object] | None:
    execution_plan = build_action_map_execution_plan(query)
    if execution_plan is None:
        return None

    executed_count = 0
    api_ready_count = 0
    blocked_count = 0
    manual_count = 0
    failed_count = 0
    step_results: list[dict[str, object]] = []
    for raw_step in execution_plan.get("steps", []):
        if not isinstance(raw_step, dict):
            continue
        step = dict(raw_step)
        status = str(step.get("status", "")).strip()
        if status == "ready_to_launch":
            target = _action_target_from_step(step)
            if target is None:
                step["status"] = "blocked"
                step["status_reason"] = "missing_launch_target"
                step["result_text"] = _blocked_step_message(step)
                blocked_count += 1
            else:
                result = execute_action(target)
                step["action_type"] = target.action_type
                step["target"] = target.target
                step["result_text"] = result.display_response
                step["spoken_result"] = result.spoken_response
                if result.success:
                    step["status"] = "executed"
                    step["status_reason"] = "launch_executed"
                    executed_count += 1
                else:
                    step["status"] = "failed"
                    step["status_reason"] = result.error_message or "launch_failed"
                    failed_count += 1
        elif status == "api_ready":
            step["result_text"] = f"{str(step.get('api_provider', '')).strip() or 'API'} 연동 준비 완료"
            api_ready_count += 1
        elif status == "blocked":
            step["result_text"] = _blocked_step_message(step)
            blocked_count += 1
        else:
            step["result_text"] = "수동 실행 단계입니다."
            manual_count += 1
        step_results.append(step)

    title = str(execution_plan.get("title", "")).strip() or str(execution_plan.get("map_id", "")).strip() or "Action Map"
    summary_parts: list[str] = []
    if executed_count:
        summary_parts.append(f"{executed_count}개 단계는 바로 실행했습니다")
    if api_ready_count:
        summary_parts.append(f"{api_ready_count}개 단계는 API 후속 제어 준비 상태입니다")
    if blocked_count:
        summary_parts.append(f"{blocked_count}개 단계는 추가 설정이 필요합니다")
    if manual_count:
        summary_parts.append(f"{manual_count}개 단계는 수동 확인 대상입니다")
    if failed_count:
        summary_parts.append(f"{failed_count}개 단계는 실행에 실패했습니다")
    if not summary_parts:
        summary_parts.append("실행 가능한 단계가 없었습니다")
    response_text = f"{title} 액션맵을 처리했습니다. {'. '.join(summary_parts)}."

    trigger_query = str(execution_plan.get("trigger_query", "")).strip()
    suggested_replies = [
        item
        for item in [trigger_query, f"{title} 다시 실행", "Skills 열기"]
        if str(item).strip()
    ]

    return {
        "query": query,
        "response": response_text,
        "spoken_response": response_text,
        "has_evidence": False,
        "citations": [],
        "status": _builtin_status_payload(),
        "render_hints": {
            "response_type": "action_result",
            "primary_source_type": "none",
            "source_profile": "action_map",
            "interaction_mode": "action_execution",
            "citation_count": 0,
            "truncated": False,
        },
        "exploration": _empty_exploration_state(),
        "guide_directive": {
            "intent": "action_map_execute",
            "skill": str(execution_plan.get("map_id", "")).strip(),
            "loop_stage": "presenting",
            "clarification_prompt": "",
            "missing_slots": [],
            "suggested_replies": suggested_replies[:3],
            "should_hold": False,
        },
        "answer_kind": "action_result",
        "task_id": "action_map_execute",
        "structured_payload": {
            "map_id": str(execution_plan.get("map_id", "")).strip(),
            "title": title,
            "description": str(execution_plan.get("description", "")).strip(),
            "trigger_query": trigger_query,
            "matched_query": str(execution_plan.get("matched_query", "")).strip(),
            "match_score": int(execution_plan.get("match_score", 0) or 0),
            "node_count": int(execution_plan.get("node_count", 0) or 0),
            "edge_count": int(execution_plan.get("edge_count", 0) or 0),
            "summary": {
                "executed": executed_count,
                "api_ready": api_ready_count,
                "blocked": blocked_count,
                "manual": manual_count,
                "failed": failed_count,
            },
            "steps": step_results,
        },
        "ui_hints": {
            "show_documents": False,
            "show_repository": False,
            "show_inspector": False,
            "preferred_view": "dashboard",
        },
    }


def _session_state_key(session_id: str) -> str:
    normalized = str(session_id or "").strip()
    return normalized or "_default"


def _normalize_document_target(target: dict[str, object]) -> dict[str, object]:
    title = str(target.get("title", "")).strip()
    path = str(target.get("path", "")).strip()
    full_path = str(target.get("full_path", "")).strip()
    preview = str(target.get("preview", "")).strip()
    kind = str(target.get("kind", "")).strip()
    if not full_path and path:
        full_path = _resolve_full_path(path, path)
    if not kind:
        suffix = Path(full_path or path).suffix.lower()
        kind = "document" if suffix in _DOCUMENT_EXTENSIONS else "filename"
    exploration = target.get("exploration")
    if not isinstance(exploration, dict):
        exploration = _build_single_target_exploration(
            label=title or Path(full_path or path).name,
            path=path or full_path,
            preview=preview,
            kind=kind,
        )
    return {
        "title": title or Path(full_path or path).name,
        "path": path or full_path,
        "full_path": full_path or path,
        "preview": preview,
        "kind": kind,
        "exploration": exploration,
    }


def _iter_session_document_targets(session_id: str) -> list[dict[str, object]]:
    key = _session_state_key(session_id)
    with _session_document_state_lock:
        state = dict(_session_document_state.get(key, {}))
    targets: list[dict[str, object]] = []
    active_target = state.get("active_target")
    if isinstance(active_target, dict):
        targets.append(_normalize_document_target(active_target))
    for candidate in state.get("recent_targets", []):
        if not isinstance(candidate, dict):
            continue
        normalized = _normalize_document_target(candidate)
        if any(
            str(existing.get("full_path", "")).strip() == str(normalized.get("full_path", "")).strip()
            for existing in targets
        ):
            continue
        targets.append(normalized)
    return targets


def _session_document_state_value(session_id: str, key: str) -> object:
    state_key = _session_state_key(session_id)
    with _session_document_state_lock:
        state = _session_document_state.get(state_key, {})
        return state.get(key)


def _remember_document_target(
    session_id: str,
    target: dict[str, object],
    *,
    section_kind: str | None = None,
    section_index: int | None = None,
    sheet_name: str | None = None,
    sheet_index: int | None = None,
) -> None:
    normalized_target = _normalize_document_target(target)
    if not str(normalized_target.get("full_path", "")).strip():
        return
    state_key = _session_state_key(session_id)
    with _session_document_state_lock:
        previous = dict(_session_document_state.get(state_key, {}))
        recent_targets = [
            normalized_target,
            *[
                _normalize_document_target(item)
                for item in previous.get("recent_targets", [])
                if isinstance(item, dict)
                and str(_normalize_document_target(item).get("full_path", "")).strip()
                != str(normalized_target.get("full_path", "")).strip()
            ],
        ][:4]
        next_state: dict[str, object] = {
            **previous,
            "active_target": normalized_target,
            "recent_targets": recent_targets,
        }
        if section_kind:
            next_state["last_section_kind"] = section_kind
        if isinstance(section_index, int):
            next_state["last_section_index"] = section_index
        if sheet_name:
            next_state["last_sheet_name"] = sheet_name
        if isinstance(sheet_index, int):
            next_state["last_sheet_index"] = sheet_index
        _session_document_state[state_key] = next_state


def _remember_relative_date_payload(session_id: str, payload: dict[str, object]) -> None:
    target_date = str(payload.get("target_date", "")).strip()
    if not target_date:
        return
    state_key = _session_state_key(session_id)
    with _session_document_state_lock:
        previous = dict(_session_document_state.get(state_key, {}))
        previous["last_relative_date"] = {
            "anchor_label": str(payload.get("anchor_label", "")).strip(),
            "anchor_date": str(payload.get("anchor_date", "")).strip(),
            "anchor_formatted": str(payload.get("anchor_formatted", "")).strip(),
            "offset_days": int(payload.get("offset_days", 0) or 0),
            "target_date": target_date,
            "target_formatted": str(payload.get("target_formatted", "")).strip(),
        }
        _session_document_state[state_key] = previous


def _session_relative_date_state(session_id: str) -> dict[str, object] | None:
    value = _session_document_state_value(session_id, "last_relative_date")
    return dict(value) if isinstance(value, dict) else None


def _remember_calendar_action_payload(session_id: str, payload: dict[str, object], *, task_id: str = "calendar_create") -> None:
    target_date = str(payload.get("target_date", "")).strip()
    if not target_date:
        return
    state_key = _session_state_key(session_id)
    with _session_document_state_lock:
        previous = dict(_session_document_state.get(state_key, {}))
        previous["last_calendar_date"] = {
            "target_date": target_date,
            "target_formatted": str(payload.get("target_formatted", "")).strip(),
            "title": str(payload.get("title", "")).strip(),
            "location": str(payload.get("location", "")).strip(),
            "calendar_name": str(payload.get("calendar_name", "")).strip(),
        }
        previous["last_action_result"] = {
            "task_id": task_id,
            "title": str(payload.get("title", "")).strip(),
            "status": str(payload.get("status", "")).strip(),
            "target_date": target_date,
        }
        _session_document_state[state_key] = previous


def _reset_session_document_state_for_tests() -> None:
    with _session_document_state_lock:
        _session_document_state.clear()


def _calendar_now() -> datetime:
    return builtin_capabilities_module._now_in_zone("Asia/Seoul")


def _format_calendar_date(value: datetime) -> str:
    return builtin_capabilities_module._format_date(value)


def _format_calendar_time_label(value: datetime) -> str:
    hour = value.hour
    minute = value.minute
    meridiem = "오전" if hour < 12 else "오후"
    display_hour = hour % 12 or 12
    return f"{meridiem} {display_hour}:{minute:02d}"


def _parse_absolute_calendar_date(query: str) -> dict[str, object] | None:
    match = _CALENDAR_ABSOLUTE_DATE_RE.search(query)
    if match is None:
        return None
    try:
        if match.group("iso_year"):
            year = int(match.group("iso_year"))
            month = int(match.group("iso_month"))
            day = int(match.group("iso_day"))
        else:
            reference = _calendar_now()
            year = int(match.group("year") or reference.year)
            month = int(match.group("month"))
            day = int(match.group("day"))
        resolved = _calendar_now().replace(
            year=year,
            month=month,
            day=day,
            hour=0,
            minute=0,
            second=0,
            microsecond=0,
        )
    except Exception:
        return None
    return {
        "anchor_label": "명시 날짜",
        "anchor_date": resolved.strftime("%Y-%m-%d"),
        "anchor_formatted": _format_calendar_date(resolved),
        "offset_days": 0,
        "target_date": resolved.strftime("%Y-%m-%d"),
        "target_formatted": _format_calendar_date(resolved),
    }


def _iter_absolute_calendar_dates(query: str) -> list[dict[str, object]]:
    results: list[dict[str, object]] = []
    reference = _calendar_now()
    for match in _CALENDAR_ABSOLUTE_DATE_RE.finditer(query):
        try:
            if match.group("iso_year"):
                year = int(match.group("iso_year"))
                month = int(match.group("iso_month"))
                day = int(match.group("iso_day"))
            else:
                year = int(match.group("year") or reference.year)
                month = int(match.group("month"))
                day = int(match.group("day"))
            resolved = reference.replace(
                year=year,
                month=month,
                day=day,
                hour=0,
                minute=0,
                second=0,
                microsecond=0,
            )
        except Exception:
            continue
        results.append(
            {
                "start": match.start(),
                "end": match.end(),
                "date": resolved,
                "date_iso": resolved.strftime("%Y-%m-%d"),
                "date_formatted": _format_calendar_date(resolved),
            }
        )
    return results


def _extract_calendar_update_delta_days(query: str) -> int | None:
    match = _CALENDAR_UPDATE_DELTA_RE.search(query)
    if match is None:
        return None
    if match.group("number"):
        value = int(match.group("number"))
    else:
        value = int(_NAMED_DAY_DELTAS.get(str(match.group("word") or "").strip(), 0))
    direction = str(match.group("direction") or "").strip()
    return -value if direction == "전" else value


def _resolve_calendar_date_payload(query: str, *, session_id: str = "") -> dict[str, object] | None:
    normalized = " ".join(query.split()).strip()
    if not normalized:
        return None
    if _CALENDAR_DEICTIC_DATE_RE.search(normalized):
        relative_date = _session_relative_date_state(session_id)
        if relative_date is not None:
            return relative_date
        return None

    explicit_date = _parse_absolute_calendar_date(normalized)
    if explicit_date is not None:
        return explicit_date

    anchor = builtin_capabilities_module._extract_relative_day_anchor(normalized)
    delta_days = builtin_capabilities_module._extract_relative_day_delta(normalized)
    if anchor is None and delta_days is None:
        return None

    now = _calendar_now()
    if anchor is None:
        anchor_label, anchor_offset = "오늘", 0
    else:
        anchor_label, anchor_offset = anchor
    anchor_date = (now + timedelta(days=anchor_offset)).replace(
        hour=0,
        minute=0,
        second=0,
        microsecond=0,
    )
    target_date = anchor_date + timedelta(days=delta_days or 0)
    return {
        "anchor_label": anchor_label,
        "anchor_date": anchor_date.strftime("%Y-%m-%d"),
        "anchor_formatted": _format_calendar_date(anchor_date),
        "offset_days": int(delta_days or 0),
        "target_date": target_date.strftime("%Y-%m-%d"),
        "target_formatted": _format_calendar_date(target_date),
    }


def _extract_calendar_duration_minutes(query: str) -> int:
    match = _CALENDAR_DURATION_RE.search(query)
    if match is None:
        return 60
    value = int(match.group("value"))
    unit = str(match.group("unit") or "").lower()
    if unit.startswith("시") or unit.startswith("hour") or unit.startswith("hr"):
        return max(30, value * 60)
    return max(15, value)


def _extract_calendar_time_payload(query: str, *, target_date: datetime) -> dict[str, object]:
    duration_minutes = _extract_calendar_duration_minutes(query)
    match = _CALENDAR_TIME_RE.search(query)
    colon_match = _CALENDAR_COLON_TIME_RE.search(query)
    assumed_afternoon = False
    if match is None and colon_match is None:
        start_at = target_date.replace(hour=0, minute=0, second=0, microsecond=0)
        end_at = start_at + timedelta(days=1)
        return {
            "all_day": True,
            "start_at": start_at,
            "end_at": end_at,
            "start_label": "종일",
            "end_label": "",
            "assumed_afternoon": False,
        }

    if match is not None:
        hour = int(match.group("hour") or 0)
        minute = int(match.group("minute") or 0)
        meridiem = str(match.group("meridiem") or "").strip()
    else:
        hour = int(colon_match.group("hour") or 0)
        minute = int(colon_match.group("minute") or 0)
        meridiem = ""

    if meridiem == "오후" and hour < 12:
        hour += 12
    elif meridiem == "오전" and hour == 12:
        hour = 0
    elif not meridiem and 1 <= hour <= 7:
        hour += 12
        assumed_afternoon = True

    start_at = target_date.replace(hour=hour, minute=minute, second=0, microsecond=0)
    end_at = start_at + timedelta(minutes=duration_minutes)
    return {
        "all_day": False,
        "start_at": start_at,
        "end_at": end_at,
        "start_label": _format_calendar_time_label(start_at),
        "end_label": _format_calendar_time_label(end_at),
        "assumed_afternoon": assumed_afternoon,
    }


def _extract_calendar_subject_payload(query: str) -> dict[str, str] | None:
    normalized = " ".join(query.split()).strip()
    if not normalized:
        return None

    quoted_match = re.search(r"[\"'“”‘’](?P<title>[^\"'“”‘’]+)[\"'“”‘’]", normalized)
    if quoted_match is not None:
        title = str(quoted_match.group("title") or "").strip()
        if title and not _CALENDAR_GENERIC_TITLE_RE.fullmatch(title):
            return {"title": title, "location": ""}

    candidate = normalized
    candidate = _CALENDAR_ABSOLUTE_DATE_RE.sub(" ", candidate)
    candidate = builtin_capabilities_module._WHITESPACE_RE.sub(" ", candidate).strip()
    candidate = re.sub(r"(?:앞으로\s*)?\d+\s*일\s*(?:후|뒤|전)(?:에)?", " ", candidate, flags=re.IGNORECASE)
    candidate = re.sub(
        r"(오늘\s*부터|내일\s*부터|모레\s*부터|글피\s*부터|어제\s*부터|엊그제\s*부터|그제\s*부터|오늘부터|내일부터|모레부터|글피부터|어제부터|엊그제부터|그제부터|오늘|내일|모레|글피|어제|엊그제|그제|그날|그때|해당\s*날짜)",
        " ",
        candidate,
        flags=re.IGNORECASE,
    )
    candidate = _CALENDAR_TIME_RE.sub(" ", candidate)
    candidate = _CALENDAR_COLON_TIME_RE.sub(" ", candidate)
    candidate = _CALENDAR_DURATION_RE.sub(" ", candidate)
    candidate = _CALENDAR_TITLE_STRIP_RE.sub(" ", candidate)
    candidate = re.sub(r"[,\.\?!]", " ", candidate)
    candidate = re.sub(r"(?:을|를|에|으로|로)\s*일정$", " ", candidate)
    candidate = re.sub(r"(해야\s*돼|해야\s*해|해야\s*합니다|가야\s*돼|가야\s*해|가야\s*합니다|예정(?:이야|입니다)?|좀|한번)$", " ", candidate)
    candidate = " ".join(candidate.split()).strip(" .")

    visit_match = re.search(
        r"(?P<place>.+?)\s*방문\s*(?:해야\s*돼|해야\s*해|해야\s*합니다|예정(?:이야|입니다)?|$)",
        candidate,
    )
    if visit_match is not None:
        location = str(visit_match.group("place") or "").strip(" .")
        location = re.sub(r"(에|에서|으로|로)$", "", location).strip(" .")
        if location:
            return {
                "title": f"{location} 방문",
                "location": location,
            }

    candidate = re.sub(
        r"^(?:일정|회의|미팅|약속|캘린더|calendar|meeting|schedule)\s*",
        "",
        candidate,
        flags=re.IGNORECASE,
    ).strip(" .")
    candidate = re.sub(r"(해야\s*돼|해야\s*해|해야\s*합니다|가야\s*돼|가야\s*해|가야\s*합니다)$", "", candidate).strip(" .")
    if not candidate or _CALENDAR_GENERIC_TITLE_RE.fullmatch(candidate):
        return None
    return {
        "title": candidate,
        "location": "",
    }


def _extract_calendar_update_request(query: str) -> dict[str, object] | None:
    normalized = " ".join(query.split()).strip()
    if not normalized:
        return None
    absolute_dates = _iter_absolute_calendar_dates(normalized)
    source_date_payload = absolute_dates[0] if absolute_dates else None
    if source_date_payload is None:
        return None

    target_date: datetime | None = None
    target_hint_segment = normalized
    if len(absolute_dates) >= 2:
        target_date = absolute_dates[1]["date"]
        target_hint_segment = normalized[absolute_dates[1]["start"] :]
    else:
        delta_days = _extract_calendar_update_delta_days(normalized)
        if delta_days is not None:
            target_date = source_date_payload["date"] + timedelta(days=delta_days)
            target_hint_segment = normalized[source_date_payload["end"] :]

    if target_date is None:
        return None

    title_segment_end = absolute_dates[1]["start"] if len(absolute_dates) >= 2 else len(normalized)
    title_segment = normalized[source_date_payload["end"] : title_segment_end]
    title_segment = _CALENDAR_UPDATE_PREFIX_RE.sub("", title_segment)
    title_segment = re.sub(r"^\s*일정(?:에서)?\s*", "", title_segment, flags=re.IGNORECASE)
    title_segment = re.sub(r"(?:을|를)\s*$", "", title_segment).strip(" .")
    title_segment = re.sub(r"\s{2,}", " ", title_segment)
    source_title_payload = _extract_calendar_subject_payload(title_segment)
    if source_title_payload is None:
        source_title_payload = _extract_calendar_subject_payload(normalized)
    if source_title_payload is None:
        return None

    target_time_payload = _extract_calendar_time_payload(
        target_hint_segment,
        target_date=target_date.replace(hour=0, minute=0, second=0, microsecond=0),
    )
    return {
        "source_date": source_date_payload["date"],
        "source_date_iso": source_date_payload["date_iso"],
        "source_date_formatted": source_date_payload["date_formatted"],
        "title": str(source_title_payload.get("title", "")).strip(),
        "title_query": str(source_title_payload.get("title", "")).strip(),
        "target_date": target_date,
        "target_date_iso": target_date.strftime("%Y-%m-%d"),
        "target_date_formatted": _format_calendar_date(target_date),
        "target_time_payload": target_time_payload,
    }


def _calendar_month_start(reference: datetime, offset: int = 0) -> datetime:
    month_index = (reference.year * 12) + (reference.month - 1) + offset
    year = month_index // 12
    month = (month_index % 12) + 1
    return reference.replace(
        year=year,
        month=month,
        day=1,
        hour=0,
        minute=0,
        second=0,
        microsecond=0,
    )


def _resolve_calendar_view_window(query: str, session_id: str = "") -> dict[str, object]:
    normalized = " ".join(query.split()).strip()
    today_start = _calendar_now().replace(hour=0, minute=0, second=0, microsecond=0)

    if re.search(r"다음\s*달|다음달", normalized, re.IGNORECASE):
        start_at = _calendar_month_start(today_start, 1)
        end_at = _calendar_month_start(today_start, 2)
        return {"range_kind": "month", "range_label": "다음 달", "start_at": start_at, "end_at": end_at}
    if re.search(r"이번\s*달|이번달", normalized, re.IGNORECASE):
        start_at = _calendar_month_start(today_start, 0)
        end_at = _calendar_month_start(today_start, 1)
        return {"range_kind": "month", "range_label": "이번 달", "start_at": start_at, "end_at": end_at}
    if re.search(r"다음\s*주", normalized, re.IGNORECASE):
        week_start = today_start - timedelta(days=today_start.weekday()) + timedelta(days=7)
        return {
            "range_kind": "week",
            "range_label": "다음 주",
            "start_at": week_start,
            "end_at": week_start + timedelta(days=7),
        }
    if re.search(r"이번\s*주", normalized, re.IGNORECASE):
        week_start = today_start - timedelta(days=today_start.weekday())
        return {
            "range_kind": "week",
            "range_label": "이번 주",
            "start_at": week_start,
            "end_at": week_start + timedelta(days=7),
        }
    if re.search(r"내일", normalized, re.IGNORECASE):
        start_at = today_start + timedelta(days=1)
        return {"range_kind": "day", "range_label": "내일", "start_at": start_at, "end_at": start_at + timedelta(days=1)}
    if re.search(r"오늘", normalized, re.IGNORECASE):
        return {"range_kind": "day", "range_label": "오늘", "start_at": today_start, "end_at": today_start + timedelta(days=1)}

    relative_payload = _resolve_calendar_date_payload(normalized, session_id=session_id)
    if relative_payload is not None:
        target_date = str(relative_payload.get("target_date", "")).strip()
        if target_date:
            resolved = datetime.fromisoformat(target_date).replace(
                tzinfo=today_start.tzinfo,
                hour=0,
                minute=0,
                second=0,
                microsecond=0,
            )
            return {
                "range_kind": "day",
                "range_label": str(relative_payload.get("target_formatted", "")).strip() or "해당 날짜",
                "start_at": resolved,
                "end_at": resolved + timedelta(days=1),
            }

    return {"range_kind": "day", "range_label": "오늘", "start_at": today_start, "end_at": today_start + timedelta(days=1)}


def _apple_script_text(value: str) -> str:
    return value.replace("\\", "\\\\").replace("\"", "\\\"")


def _apple_script_date_block(var_name: str, value: datetime) -> str:
    month_name = _APPLE_SCRIPT_MONTH_NAMES[value.month]
    seconds = (value.hour * 60 * 60) + (value.minute * 60) + value.second
    return "\n".join(
        [
            f"set {var_name} to current date",
            f"set year of {var_name} to {value.year}",
            f"set month of {var_name} to {month_name}",
            f"set day of {var_name} to {value.day}",
            f"set time of {var_name} to {seconds}",
        ]
    )


def _create_local_calendar_event(
    *,
    title: str,
    start_at: datetime,
    end_at: datetime,
    all_day: bool,
    location: str = "",
    notes: str = "",
) -> dict[str, str]:
    calendar_name_assignment = "set calendarName to name"
    property_segments = [
        f'summary:"{_apple_script_text(title)}"',
        "start date:startDate",
        "end date:endDate",
    ]
    script = "\n".join(
        [
            _apple_script_date_block("startDate", start_at),
            _apple_script_date_block("endDate", end_at),
            'tell application "Calendar"',
            "if (count of calendars) is 0 then error \"No calendars available\"",
            "tell first calendar",
            calendar_name_assignment,
            f"set newEvent to make new event at end of events with properties {{{', '.join(property_segments)}}}",
            (
                f'set location of newEvent to "{_apple_script_text(location.strip())}"'
                if location.strip()
                else ""
            ),
            (
                f'set description of newEvent to "{_apple_script_text(notes.strip())}"'
                if notes.strip()
                else ""
            ),
            "set allday event of newEvent to true" if all_day else "",
            'return calendarName & "\t" & (summary of newEvent)',
            "end tell",
            "end tell",
        ]
    )
    completed = subprocess.run(
        ["osascript", "-e", script],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    if completed.returncode != 0:
        error_text = completed.stderr.strip() or completed.stdout.strip() or "macOS Calendar event creation failed"
        raise RuntimeError(error_text)
    output = completed.stdout.strip()
    parts = output.split("\t", 1) if output else []
    return {
        "calendar_name": parts[0].strip() if parts else "Calendar",
        "event_title": parts[1].strip() if len(parts) > 1 else title,
    }


def _update_local_calendar_event(
    *,
    title_query: str,
    source_date: datetime,
    target_date: datetime,
    explicit_start_at: datetime | None,
) -> dict[str, str]:
    source_date = source_date.replace(hour=0, minute=0, second=0, microsecond=0)
    target_date = target_date.replace(hour=0, minute=0, second=0, microsecond=0)
    explicit_time = explicit_start_at is not None
    if explicit_start_at is None:
        explicit_start_at = target_date

    script_lines = [
        "on normalizeText(theText)",
        'set AppleScript\'s text item delimiters to {" ", tab}',
        "set rawItems to every text item of (theText as text)",
        'set AppleScript\'s text item delimiters to ""',
        "set joinedText to rawItems as text",
        'set AppleScript\'s text item delimiters to ""',
        "return joinedText",
        "end normalizeText",
        _apple_script_date_block("sourceStart", source_date),
        "set sourceEnd to sourceStart + (24 * 60 * 60)",
        _apple_script_date_block("targetDay", target_date),
        _apple_script_date_block("explicitStart", explicit_start_at),
        f'set normalizedQuery to my normalizeText("{_apple_script_text(title_query)}")',
        f'set explicitTime to {"true" if explicit_time else "false"}',
        'tell application "Calendar"',
        "repeat with currentCalendar in calendars",
        "set calendarName to name of currentCalendar",
        "repeat with matchedEvent in events of currentCalendar",
        "set eventStart to start date of matchedEvent",
        "if eventStart ≥ sourceStart and eventStart < sourceEnd then",
        "set normalizedSummary to my normalizeText(summary of matchedEvent)",
        "if normalizedSummary contains normalizedQuery then",
        "set durationSeconds to (end date of matchedEvent) - (start date of matchedEvent)",
        "if explicitTime then",
        "set newStart to explicitStart",
        "if allday event of matchedEvent then",
        "set newEnd to newStart + (60 * 60)",
        "else",
        "if durationSeconds < 60 then set durationSeconds to (60 * 60)",
        "set newEnd to newStart + durationSeconds",
        "end if",
        "set start date of matchedEvent to newStart",
        "set end date of matchedEvent to newEnd",
        "set allday event of matchedEvent to false",
        "else",
        "if allday event of matchedEvent then",
        "set newStart to targetDay",
        "set newEnd to targetDay + (24 * 60 * 60)",
        "set start date of matchedEvent to newStart",
        "set end date of matchedEvent to newEnd",
        "set allday event of matchedEvent to true",
        "else",
        "set originalTimeSeconds to time of eventStart",
        "set newStart to targetDay",
        "set time of newStart to originalTimeSeconds",
        "set newEnd to newStart + durationSeconds",
        "set start date of matchedEvent to newStart",
        "set end date of matchedEvent to newEnd",
        "set allday event of matchedEvent to false",
        "end if",
        "end if",
        'return calendarName & "\t" & (summary of matchedEvent)',
        "end if",
        "end if",
        "end repeat",
        "end repeat",
        'error "No matching event found"',
        "end tell",
    ]
    script = "\n".join(script_lines)
    completed = subprocess.run(
        ["osascript", "-e", script],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    if completed.returncode != 0:
        error_text = completed.stderr.strip() or completed.stdout.strip() or "macOS Calendar event update failed"
        raise RuntimeError(error_text)
    output = completed.stdout.strip()
    parts = output.split("\t", 1) if output else []
    return {
        "calendar_name": parts[0].strip() if parts else "Calendar",
        "event_title": parts[1].strip() if len(parts) > 1 else title_query,
    }


def _list_local_calendar_events(*, start_at: datetime, end_at: datetime) -> list[dict[str, object]]:
    range_days = max(1, int((end_at - start_at).total_seconds() // 86400))
    timeout_seconds = 25 if range_days >= 28 else 15 if range_days >= 7 else 10
    swift_path = Path(__file__).with_name("calendar_query.swift")
    if not swift_path.exists():
        raise RuntimeError("calendar_query.swift helper를 찾지 못했습니다.")

    try:
        completed = subprocess.run(
            [
                "/usr/bin/swift",
                str(swift_path),
                start_at.isoformat(),
                end_at.isoformat(),
            ],
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"Calendar 조회가 {timeout_seconds}초를 넘겨 중단되었습니다.") from exc

    if completed.returncode != 0:
        error_text = completed.stderr.strip() or completed.stdout.strip() or "macOS Calendar event lookup failed"
        raise RuntimeError(error_text)

    output = completed.stdout.strip()
    if not output:
        return []

    try:
        records = json.loads(output)
    except Exception as exc:
        raise RuntimeError("Calendar 조회 결과를 해석하지 못했습니다.") from exc

    if not isinstance(records, list):
        raise RuntimeError("Calendar 조회 결과 형식이 올바르지 않습니다.")

    results: list[dict[str, object]] = []
    for item in records:
        if not isinstance(item, dict):
            continue
        start_raw = str(item.get("start_at", "")).strip()
        end_raw = str(item.get("end_at", "")).strip()
        try:
            start_dt = datetime.fromisoformat(start_raw.replace("Z", "+00:00")) if start_raw else None
            end_dt = datetime.fromisoformat(end_raw.replace("Z", "+00:00")) if end_raw else None
        except Exception:
            start_dt = None
            end_dt = None
        all_day = bool(item.get("all_day", False))
        results.append(
            {
                "calendar_name": str(item.get("calendar_name", "")).strip() or "Calendar",
                "title": str(item.get("title", "")).strip() or "Untitled event",
                "location": str(item.get("location", "")).strip(),
                "start_at": start_dt or start_raw,
                "end_at": end_dt or end_raw,
                "all_day": all_day,
                "start_label": "종일 일정" if all_day or start_dt is None else _format_calendar_time_label(start_dt),
                "end_label": "" if all_day or end_dt is None else _format_calendar_time_label(end_dt),
                "date_label": _format_calendar_date(start_dt) if isinstance(start_dt, datetime) else start_raw.split("T", 1)[0],
            }
        )

    results.sort(key=lambda item: (str(item["date_label"]), str(item["start_label"]), str(item["title"])))
    return results


def _build_calendar_clarification_payload(
    *,
    query: str,
    task_id: str,
    prompt: str,
    missing_slots: list[str],
    target_payload: dict[str, object] | None = None,
) -> dict[str, object]:
    if task_id == "calendar_followup":
        skill_id = "builtin_calendar_followup"
    elif task_id == "calendar_update":
        skill_id = "macos_calendar_update_event"
    else:
        skill_id = "macos_calendar_create_event"
    target_date = ""
    target_formatted = ""
    if isinstance(target_payload, dict):
        target_date = str(target_payload.get("target_date", "")).strip()
        target_formatted = str(target_payload.get("target_formatted", "")).strip()
    return {
        "query": query,
        "response": prompt,
        "spoken_response": prompt,
        "has_evidence": False,
        "citations": [],
        "status": _builtin_status_payload(),
        "render_hints": {
            "response_type": "builtin_answer",
            "primary_source_type": "none",
            "source_profile": "calendar",
            "interaction_mode": "calendar_clarification",
            "citation_count": 0,
            "truncated": False,
        },
        "exploration": _empty_exploration_state(),
        "guide_directive": {
            "intent": task_id,
            "skill": skill_id,
            "loop_stage": "waiting_user_reply",
            "clarification_prompt": prompt,
            "missing_slots": missing_slots,
            "suggested_replies": [
                reply
                for reply in [
                    f"{target_formatted}에 어떤 일정을 만들까요?" if target_formatted else "",
                    "회의 제목을 알려줘",
                    "캘린더 열어줘",
                ]
                if str(reply).strip()
            ][:3],
            "should_hold": True,
        },
        "answer_kind": "utility_result",
        "task_id": task_id,
        "structured_payload": {
            "status": "clarification_required",
            "target_date": target_date,
            "target_formatted": target_formatted,
            "missing_slots": missing_slots,
        },
        "ui_hints": {
            "show_documents": False,
            "show_repository": False,
            "show_inspector": False,
            "preferred_view": "dashboard",
        },
    }


def _resolve_calendar_update_payload(query: str, session_id: str = "") -> dict[str, object] | None:
    normalized = " ".join(query.split()).strip()
    if not normalized:
        return None

    request = _extract_calendar_update_request(normalized)
    if request is None:
        return _build_calendar_clarification_payload(
            query=query,
            task_id="calendar_update",
            prompt="어떤 일정을 어느 날짜나 시간으로 수정할지 알려주세요.",
            missing_slots=["source_event", "target_date"],
        )

    title_query = str(request.get("title_query", "")).strip()
    source_date = request["source_date"]
    target_date = request["target_date"]
    target_time_payload = request["target_time_payload"]
    explicit_start_at = None if bool(target_time_payload.get("all_day", True)) else target_time_payload.get("start_at")

    try:
        updated = _update_local_calendar_event(
            title_query=title_query,
            source_date=source_date,
            target_date=target_date,
            explicit_start_at=explicit_start_at if isinstance(explicit_start_at, datetime) else None,
        )
    except Exception as exc:
        response_text = (
            f"{str(request.get('source_date_formatted', '')).strip()}의 '{title_query}' 일정을 수정하려 했지만 실패했습니다. "
            f"{str(exc).strip() or 'Calendar에서 일정을 찾지 못했거나 수정 권한이 없습니다.'}"
        )
        return {
            "query": query,
            "response": response_text,
            "spoken_response": response_text,
            "has_evidence": False,
            "citations": [],
            "status": _builtin_status_payload(),
            "render_hints": {
                "response_type": "action_result",
                "primary_source_type": "none",
                "source_profile": "calendar",
                "interaction_mode": "calendar_update",
                "citation_count": 0,
                "truncated": False,
            },
            "exploration": _empty_exploration_state(),
            "guide_directive": {
                "intent": "calendar_update",
                "skill": "macos_calendar_update_event",
                "loop_stage": "presenting",
                "clarification_prompt": "",
                "missing_slots": [],
                "suggested_replies": ["캘린더 열어줘", "일정 제목을 더 구체적으로 알려줄게"],
                "should_hold": False,
            },
            "answer_kind": "action_result",
            "task_id": "calendar_update",
            "structured_payload": {
                "status": "failed",
                "provider": "macos_calendar",
                "title": title_query,
                "source_date": str(request.get("source_date_iso", "")).strip(),
                "source_date_formatted": str(request.get("source_date_formatted", "")).strip(),
                "target_date": str(request.get("target_date_iso", "")).strip(),
                "target_date_formatted": str(request.get("target_date_formatted", "")).strip(),
                "error": str(exc).strip(),
            },
            "ui_hints": {
                "show_documents": False,
                "show_repository": False,
                "show_inspector": False,
                "preferred_view": "dashboard",
            },
        }

    response_text = (
        f"'{title_query}' 일정을 {str(request.get('target_date_formatted', '')).strip()}로 수정했습니다."
    )
    if bool(target_time_payload.get("all_day", True)):
        response_text += " 시간 지정이 없어 기존 종일 일정 또는 기존 시각 기준으로 이동했습니다."
    else:
        response_text += (
            f" 시작 시각은 {str(target_time_payload.get('start_label', '')).strip()}이고 "
            f"종료 시각은 {str(target_time_payload.get('end_label', '')).strip()}입니다."
        )

    return {
        "query": query,
        "response": response_text,
        "spoken_response": response_text,
        "has_evidence": False,
        "citations": [],
        "status": _builtin_status_payload(),
        "render_hints": {
            "response_type": "action_result",
            "primary_source_type": "none",
            "source_profile": "calendar",
            "interaction_mode": "calendar_update",
            "citation_count": 0,
            "truncated": False,
        },
        "exploration": _empty_exploration_state(),
        "guide_directive": {
            "intent": "calendar_update",
            "skill": "macos_calendar_update_event",
            "loop_stage": "presenting",
            "clarification_prompt": "",
            "missing_slots": [],
            "suggested_replies": ["캘린더 열어줘", f"{title_query} 일정 다시 수정해줘"],
            "should_hold": False,
        },
        "answer_kind": "action_result",
        "task_id": "calendar_update",
        "structured_payload": {
            "status": "updated",
            "provider": "macos_calendar",
            "calendar_name": str(updated.get("calendar_name", "")).strip(),
            "title": str(updated.get("event_title", "")).strip() or title_query,
            "source_date": str(request.get("source_date_iso", "")).strip(),
            "source_date_formatted": str(request.get("source_date_formatted", "")).strip(),
            "target_date": str(request.get("target_date_iso", "")).strip(),
            "target_date_formatted": str(request.get("target_date_formatted", "")).strip(),
            "start_at": target_time_payload["start_at"].isoformat(),
            "end_at": target_time_payload["end_at"].isoformat(),
            "start_label": str(target_time_payload.get("start_label", "")).strip(),
            "end_label": str(target_time_payload.get("end_label", "")).strip(),
            "all_day": bool(target_time_payload.get("all_day", True)),
        },
        "ui_hints": {
            "show_documents": False,
            "show_repository": False,
            "show_inspector": False,
            "preferred_view": "dashboard",
        },
    }


def _resolve_calendar_view_payload(query: str, session_id: str = "") -> dict[str, object] | None:
    normalized = " ".join(query.split()).strip()
    if not normalized:
        return None

    window = _resolve_calendar_view_window(normalized, session_id=session_id)
    start_at = window["start_at"]
    end_at = window["end_at"]
    range_label = str(window.get("range_label", "")).strip() or "일정"
    range_kind = str(window.get("range_kind", "")).strip() or "day"

    try:
        events = _list_local_calendar_events(start_at=start_at, end_at=end_at)
    except Exception as exc:
        response_text = f"{range_label} 일정을 불러오지 못했습니다. {str(exc).strip() or 'Calendar 접근 권한을 확인해 주세요.'}"
        return {
            "query": query,
            "response": response_text,
            "spoken_response": response_text,
            "has_evidence": False,
            "citations": [],
            "status": _builtin_status_payload(),
            "render_hints": {
                "response_type": "live_data_result",
                "primary_source_type": "none",
                "source_profile": "calendar",
                "interaction_mode": "calendar_view",
                "citation_count": 0,
                "truncated": False,
            },
            "exploration": _empty_exploration_state(),
            "guide_directive": {
                "intent": "calendar_today",
                "skill": "macos_calendar_agenda_view",
                "loop_stage": "presenting",
                "clarification_prompt": "",
                "missing_slots": [],
                "suggested_replies": ["캘린더 열어줘", "오늘 일정 보여줘", "이번달 일정 알려줘"],
                "should_hold": False,
            },
            "answer_kind": "live_data_result",
            "task_id": "calendar_today",
            "structured_payload": {
                "status": "failed",
                "provider": "macos_calendar",
                "range_kind": range_kind,
                "range_label": range_label,
                "start_date": start_at.strftime("%Y-%m-%d"),
                "end_date": end_at.strftime("%Y-%m-%d"),
                "event_count": 0,
                "events": [],
                "error": str(exc).strip(),
            },
            "ui_hints": {
                "show_documents": False,
                "show_repository": False,
                "show_inspector": False,
                "preferred_view": "dashboard",
            },
        }

    event_count = len(events)
    if event_count == 0:
        response_text = f"{range_label} 일정은 없습니다."
    else:
        preview_lines: list[str] = []
        for item in events[:6]:
            line = (
                f"{item['date_label']} · {item['title']}"
                if bool(item.get("all_day"))
                else f"{item['date_label']} {item['start_label']} · {item['title']}"
            )
            location = str(item.get("location", "")).strip()
            if location:
                line += f" @ {location}"
            preview_lines.append(line)
        response_text = f"{range_label} 일정 {event_count}건입니다. " + " / ".join(preview_lines)
        if event_count > 6:
            response_text += f" 외 {event_count - 6}건"

    serialized_events = [
        {
            "calendar_name": str(item.get("calendar_name", "")).strip(),
            "title": str(item.get("title", "")).strip(),
            "location": str(item.get("location", "")).strip(),
            "start_at": item["start_at"].isoformat() if isinstance(item.get("start_at"), datetime) else str(item.get("start_at", "")).strip(),
            "end_at": item["end_at"].isoformat() if isinstance(item.get("end_at"), datetime) else str(item.get("end_at", "")).strip(),
            "all_day": bool(item.get("all_day", False)),
            "start_label": str(item.get("start_label", "")).strip(),
            "end_label": str(item.get("end_label", "")).strip(),
            "date_label": str(item.get("date_label", "")).strip(),
        }
        for item in events[:24]
    ]

    return {
        "query": query,
        "response": response_text,
        "spoken_response": response_text,
        "has_evidence": False,
        "citations": [],
        "status": _builtin_status_payload(),
        "render_hints": {
            "response_type": "live_data_result",
            "primary_source_type": "none",
            "source_profile": "calendar",
            "interaction_mode": "calendar_view",
            "citation_count": 0,
            "truncated": event_count > len(serialized_events),
        },
        "exploration": _empty_exploration_state(),
        "guide_directive": {
            "intent": "calendar_today",
            "skill": "macos_calendar_agenda_view",
            "loop_stage": "presenting",
            "clarification_prompt": "",
            "missing_slots": [],
            "suggested_replies": ["내일 일정 보여줘", "이번주 일정 알려줘", "다음주 일정 브리핑"],
            "should_hold": False,
        },
        "answer_kind": "live_data_result",
        "task_id": "calendar_today",
        "structured_payload": {
            "status": "ok",
            "provider": "macos_calendar",
            "range_kind": range_kind,
            "range_label": range_label,
            "start_date": start_at.strftime("%Y-%m-%d"),
            "end_date": end_at.strftime("%Y-%m-%d"),
            "event_count": event_count,
            "events": serialized_events,
        },
        "ui_hints": {
            "show_documents": False,
            "show_repository": False,
            "show_inspector": False,
            "preferred_view": "dashboard",
        },
    }


def _resolve_calendar_create_payload(query: str, session_id: str = "") -> dict[str, object] | None:
    normalized = " ".join(query.split()).strip()
    if not normalized:
        return None

    target_payload = _resolve_calendar_date_payload(normalized, session_id=session_id)
    if target_payload is None:
        return _build_calendar_clarification_payload(
            query=query,
            task_id="calendar_create",
            prompt="어느 날짜에 일정을 등록할지 먼저 알려주세요.",
            missing_slots=["target_date"],
        )

    subject_payload = _extract_calendar_subject_payload(normalized)
    if subject_payload is None:
        return _build_calendar_clarification_payload(
            query=query,
            task_id="calendar_followup" if _CALENDAR_DEICTIC_DATE_RE.search(normalized) else "calendar_create",
            prompt="등록할 일정 제목이나 내용을 알려주세요.",
            missing_slots=["title"],
            target_payload=target_payload,
        )

    try:
        target_date = datetime.strptime(str(target_payload.get("target_date", "")).strip(), "%Y-%m-%d")
    except ValueError:
        return _build_calendar_clarification_payload(
            query=query,
            task_id="calendar_create",
            prompt="일정을 등록할 날짜를 다시 알려주세요.",
            missing_slots=["target_date"],
        )

    base_datetime = _calendar_now().replace(
        year=target_date.year,
        month=target_date.month,
        day=target_date.day,
        hour=0,
        minute=0,
        second=0,
        microsecond=0,
    )
    time_payload = _extract_calendar_time_payload(normalized, target_date=base_datetime)
    title = str(subject_payload.get("title", "")).strip()
    location = str(subject_payload.get("location", "")).strip()
    notes = normalized

    try:
        created = _create_local_calendar_event(
            title=title,
            start_at=time_payload["start_at"],
            end_at=time_payload["end_at"],
            all_day=bool(time_payload["all_day"]),
            location=location,
            notes=notes,
        )
    except Exception as exc:
        response_text = (
            f"{str(target_payload.get('target_formatted', '')).strip()} 일정으로 '{title}'를 등록하려 했지만 실패했습니다. "
            f"{str(exc).strip() or 'Calendar 접근 권한이나 기본 캘린더 설정을 확인해 주세요.'}"
        )
        return {
            "query": query,
            "response": response_text,
            "spoken_response": response_text,
            "has_evidence": False,
            "citations": [],
            "status": _builtin_status_payload(),
            "render_hints": {
                "response_type": "action_result",
                "primary_source_type": "none",
                "source_profile": "calendar",
                "interaction_mode": "calendar_create",
                "citation_count": 0,
                "truncated": False,
            },
            "exploration": _empty_exploration_state(),
            "guide_directive": {
                "intent": "calendar_create",
                "skill": "macos_calendar_create_event",
                "loop_stage": "presenting",
                "clarification_prompt": "",
                "missing_slots": [],
                "suggested_replies": ["캘린더 열어줘", "다시 시도해줘"],
                "should_hold": False,
            },
            "answer_kind": "action_result",
            "task_id": "calendar_create",
            "structured_payload": {
                "status": "failed",
                "provider": "macos_calendar",
                "title": title,
                "location": location,
                "target_date": str(target_payload.get("target_date", "")).strip(),
                "target_formatted": str(target_payload.get("target_formatted", "")).strip(),
                "error": str(exc).strip(),
            },
            "ui_hints": {
                "show_documents": False,
                "show_repository": False,
                "show_inspector": False,
                "preferred_view": "dashboard",
            },
        }

    response_text = (
        f"{str(target_payload.get('target_formatted', '')).strip()} 일정으로 '{title}'를 macOS Calendar에 등록했습니다."
    )
    if location:
        response_text += f" 위치는 {location}입니다."
    if bool(time_payload["all_day"]):
        response_text += " 시간 지정이 없어 종일 일정으로 저장했습니다."
    else:
        response_text += (
            f" 시작 시각은 {str(time_payload.get('start_label', '')).strip()}이고 "
            f"종료 시각은 {str(time_payload.get('end_label', '')).strip()}입니다."
        )
        if bool(time_payload.get("assumed_afternoon", False)):
            response_text += " 오전/오후 표기가 없어 오후 시간대로 해석했습니다."

    return {
        "query": query,
        "response": response_text,
        "spoken_response": response_text,
        "has_evidence": False,
        "citations": [],
        "status": _builtin_status_payload(),
        "render_hints": {
            "response_type": "action_result",
            "primary_source_type": "none",
            "source_profile": "calendar",
            "interaction_mode": "calendar_create",
            "citation_count": 0,
            "truncated": False,
        },
        "exploration": _empty_exploration_state(),
        "guide_directive": {
            "intent": "calendar_create",
            "skill": "macos_calendar_create_event",
            "loop_stage": "presenting",
            "clarification_prompt": "",
            "missing_slots": [],
            "suggested_replies": ["캘린더 열어줘", f"{title} 일정 다시 등록해줘"],
            "should_hold": False,
        },
        "answer_kind": "action_result",
        "task_id": "calendar_create",
        "structured_payload": {
            "status": "created",
            "provider": "macos_calendar",
            "calendar_name": str(created.get("calendar_name", "")).strip(),
            "title": title,
            "location": location,
            "target_date": str(target_payload.get("target_date", "")).strip(),
            "target_formatted": str(target_payload.get("target_formatted", "")).strip(),
            "start_at": time_payload["start_at"].isoformat(),
            "end_at": time_payload["end_at"].isoformat(),
            "start_label": str(time_payload.get("start_label", "")).strip(),
            "end_label": str(time_payload.get("end_label", "")).strip(),
            "all_day": bool(time_payload["all_day"]),
            "assumed_afternoon": bool(time_payload.get("assumed_afternoon", False)),
        },
        "ui_hints": {
            "show_documents": False,
            "show_repository": False,
            "show_inspector": False,
            "preferred_view": "dashboard",
        },
    }


def _strip_document_open_query(query: str) -> str:
    cleaned = re.sub(
        r"\b(open|show|please|document|file)\b",
        " ",
        query,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(
        r"(열어\s*줘|열어줘|열기|열어|보여\s*줘|보여줘|띄워\s*줘|띄워줘|문서|파일|자료|다시|좀|한번|확인해줘|요약|정리|개요|핵심|목차|아웃라인|헤딩|구성|슬라이드|slide|페이지|page|시트|sheet|탭|내용)",
        " ",
        cleaned,
        flags=re.IGNORECASE,
    )
    normalized = " ".join(cleaned.split()).strip(" ?.")
    return normalized or query.strip()


def _resolve_document_open_payload(query: str, session_id: str = "") -> dict[str, object] | None:
    lookup_query = _strip_document_open_query(query)
    target = _resolve_document_task_target(lookup_query, session_id=session_id)
    if target is None:
        return _build_document_task_clarification_payload(
            query=query,
            task_id="open_document",
            skill="builtin_document_open",
            prompt="어떤 문서를 열지 먼저 알려주세요.",
            session_id=session_id,
            lookup_query=lookup_query,
        )
    exploration = target["exploration"]
    candidate_labels = [
        item.get("label", "")
        for group_name in ("document_candidates", "file_candidates", "class_candidates", "function_candidates")
        for item in exploration.get(group_name, [])
        if isinstance(item, dict) and str(item.get("label", "")).strip()
    ]
    interaction_mode = str(exploration.get("mode", "")).strip() or "document_exploration"
    has_document_candidates = bool(exploration.get("document_candidates"))
    has_code_candidates = bool(exploration.get("file_candidates"))
    primary_label = str(target["title"]).strip()
    if len(candidate_labels) == 1:
        response_text = f"{primary_label} 항목을 열 수 있습니다. Documents에서 바로 확인하세요."
    else:
        response_text = (
            f"{primary_label} 포함 관련 후보 {len(candidate_labels)}개를 찾았습니다. "
            "Documents 또는 Repository에서 선택해 확인하세요."
        )

    _remember_document_target(session_id, target)
    return {
        "query": query,
        "response": response_text,
        "spoken_response": response_text,
        "has_evidence": False,
        "citations": [],
        "status": _builtin_status_payload(),
        "render_hints": {
            "response_type": "builtin_answer",
            "primary_source_type": "document" if has_document_candidates else ("code" if has_code_candidates else "none"),
            "source_profile": "document_open",
            "interaction_mode": interaction_mode,
            "citation_count": 0,
            "truncated": False,
        },
        "exploration": exploration,
        "guide_directive": {
            "intent": "open_document",
            "skill": "builtin_document_open",
            "loop_stage": "presenting",
            "clarification_prompt": "",
            "missing_slots": [],
            "suggested_replies": candidate_labels[:3],
            "should_hold": False,
        },
        "answer_kind": "retrieval_result",
        "task_id": "open_document",
        "structured_payload": {
            "candidate_count": len(candidate_labels),
            "primary_label": primary_label,
            "interaction_mode": interaction_mode,
        },
        "ui_hints": {
            "show_documents": True,
            "show_repository": True,
            "show_inspector": False,
            "preferred_view": "detail_viewer" if len(candidate_labels) == 1 else "repository",
        },
    }


def _resolve_recent_context_payload(query: str, session_id: str = "") -> dict[str, object] | None:
    candidate_contexts: list[object] = []
    seen_keys: set[str] = set()
    with _runtime_context_lock:
        if _last_runtime_context_key:
            context = _runtime_contexts.get(_last_runtime_context_key)
            if context is not None:
                candidate_contexts.append(context)
                seen_keys.add(_last_runtime_context_key)
        for key in reversed(tuple(_runtime_contexts.keys())):
            if key in seen_keys:
                continue
            context = _runtime_contexts.get(key)
            if context is not None:
                candidate_contexts.append(context)
                seen_keys.add(key)

    for context in candidate_contexts:
        orchestrator = getattr(context, "orchestrator", None)
        answer = getattr(orchestrator, "last_answer", None)
        if answer is None or not getattr(answer.evidence, "items", ()):
            continue
        error_monitor = getattr(context, "error_monitor", None)
        response_text = (
            "방금 확인한 자료를 다시 열었습니다. Documents에서 바로 확인하고 Repository로 이어서 탐색할 수 있습니다."
        )
        response = build_menu_response(
            turn=ConversationTurn(
                user_input=query,
                assistant_output=response_text,
                has_evidence=True,
            ),
            answer=answer,
            safe_mode=bool(error_monitor.safe_mode_active()) if error_monitor is not None else False,
            degraded_mode=bool(getattr(error_monitor, "degraded_mode", False)),
            generation_blocked=bool(getattr(error_monitor, "generation_blocked", False)),
            write_blocked=bool(getattr(error_monitor, "write_blocked", False)),
            rebuild_index_required=bool(getattr(error_monitor, "rebuild_index_required", False)),
            knowledge_base_path=getattr(context, "knowledge_base_path", None),
            planner_analysis=None,
        )
        payload = asdict(response)
        payload["answer_kind"] = "retrieval_result"
        payload["task_id"] = "recent_context"
        payload["structured_payload"] = {
            "citation_count": len(payload.get("citations", [])),
            "has_source_presentation": bool(payload.get("source_presentation")),
        }
        payload["ui_hints"] = {
            "show_documents": True,
            "show_repository": True,
            "show_inspector": bool(payload.get("citations")),
            "preferred_view": "detail_viewer",
        }
        if payload.get("guide_directive") is None:
            payload["guide_directive"] = {}
        first_artifact = next(
            (
                artifact
                for artifact in _build_presentation_payload(payload)[1]
                if isinstance(artifact, dict) and str(artifact.get("path", "")).strip()
            ),
            None,
        )
        if isinstance(first_artifact, dict):
            _remember_document_target(
                session_id,
                {
                    "title": str(first_artifact.get("title", "")).strip(),
                    "path": str(first_artifact.get("path", "")).strip(),
                    "full_path": str(first_artifact.get("path", "")).strip(),
                    "preview": str(first_artifact.get("preview", "")).strip(),
                    "kind": "document" if str(first_artifact.get("type", "")).strip() == "document" else "filename",
                },
            )
        return payload
    return None


def _resolve_relative_calendar_followup_payload(query: str, session_id: str = "") -> dict[str, object] | None:
    normalized = " ".join(query.split()).strip()
    lowered = normalized.lower()
    if not any(token in lowered for token in ("그날", "그때", "그 날짜", "해당 날짜", "that day", "that date")):
        return None
    if not any(token in lowered for token in ("일정", "캘린더", "calendar", "schedule", "meeting", "event", "잡아줘", "예약")):
        return None

    relative_date = _session_relative_date_state(session_id)
    if relative_date is None:
        return _build_calendar_clarification_payload(
            query=query,
            task_id="calendar_followup",
            prompt="어느 날짜 일정인지 먼저 알려주세요.",
            missing_slots=["target_date"],
        )

    response = _resolve_calendar_create_payload(query, session_id=session_id)
    if response is None:
        return _build_calendar_clarification_payload(
            query=query,
            task_id="calendar_followup",
            prompt="등록할 일정 제목이나 내용을 알려주세요.",
            missing_slots=["title"],
            target_payload=relative_date,
        )
    return response


def _iter_recent_runtime_contexts() -> list[object]:
    candidate_contexts: list[object] = []
    seen_keys: set[str] = set()
    with _runtime_context_lock:
        if _last_runtime_context_key:
            context = _runtime_contexts.get(_last_runtime_context_key)
            if context is not None:
                candidate_contexts.append(context)
                seen_keys.add(_last_runtime_context_key)
        for key in reversed(tuple(_runtime_contexts.keys())):
            if key in seen_keys:
                continue
            context = _runtime_contexts.get(key)
            if context is not None:
                candidate_contexts.append(context)
                seen_keys.add(key)
    return candidate_contexts


def _document_search_preview(path: Path) -> str:
    try:
        parsed = _document_parser.parse(path)
    except Exception:
        return ""
    lines = [line.strip() for line in parsed.splitlines() if line.strip()]
    return "\n".join(lines[:10])[:1200]


def _search_knowledge_base_candidates(
    query: str,
    *,
    limit: int,
    allowed_extensions: set[str],
) -> list[dict[str, object]]:
    kb = resolve_knowledge_base_path()
    if not kb.exists():
        return []

    normalized_query = query.strip().lower()
    query_tokens = [
        token
        for token in re.split(r"[^a-z0-9가-힣]+", normalized_query)
        if len(token) >= 2 and token not in {"문서", "파일", "자료", "요약", "정리", "목차", "아웃라인"}
    ]
    ranked: list[dict[str, object]] = []
    for path in kb.rglob("*"):
        if not path.is_file():
            continue
        suffix = path.suffix.lower()
        if suffix not in allowed_extensions:
            continue
        name_lower = path.name.lower()
        stem_lower = path.stem.lower()
        score = 0.0
        if normalized_query and normalized_query in name_lower:
            score += 2.5
        if normalized_query and normalized_query in stem_lower:
            score += 2.0
        for token in query_tokens:
            if token in name_lower:
                score += 1.2
            elif token in path.as_posix().lower():
                score += 0.6
        if score <= 0:
            continue
        relative_path = path.relative_to(kb).as_posix()
        ranked.append({
            "label": path.name,
            "kind": "document",
            "path": relative_path,
            "full_path": str(path),
            "score": round(score, 3),
            "preview": _document_search_preview(path),
        })
    ranked.sort(key=lambda item: (float(item["score"]), str(item["label"]).lower()), reverse=True)
    return ranked[: max(1, limit)]


def _search_knowledge_base_documents(query: str, *, limit: int = 4) -> list[dict[str, object]]:
    return _search_knowledge_base_candidates(
        query,
        limit=limit,
        allowed_extensions=_DOCUMENT_EXTENSIONS,
    )


def _search_knowledge_base_topic_sources(query: str, *, limit: int = 6) -> list[dict[str, object]]:
    return _search_knowledge_base_candidates(
        query,
        limit=limit,
        allowed_extensions=_TOPIC_SOURCE_EXTENSIONS,
    )


def _looks_like_document_identifier_query(query: str) -> bool:
    normalized = str(query or "").strip().lower()
    if not normalized:
        return False
    if "/" in normalized or "\\" in normalized:
        return True
    return bool(
        re.search(
            r"\.(?:py|ts|tsx|js|jsx|sql|md|txt|json|yaml|yml|csv|docx|pptx|xlsx|pdf|hwp|hwpx|html|htm)\b",
            normalized,
            re.IGNORECASE,
        )
    )


def _is_exact_document_lookup_query(query: str, candidate: dict[str, object]) -> bool:
    normalized_query = str(query or "").strip().lower()
    if not normalized_query:
        return False
    label = str(candidate.get("label", "")).strip().lower()
    path = str(candidate.get("path", "")).strip().lower()
    names = {
        label,
        path,
        Path(label).stem.lower() if label else "",
        Path(path).stem.lower() if path else "",
    }
    return normalized_query in {name for name in names if name}


def _topic_candidate_score(topic_query: str, candidate: dict[str, object]) -> float:
    normalized_query = str(topic_query or "").strip().lower()
    if not normalized_query:
        return 0.0
    title = str(candidate.get("label", "")).strip().lower()
    path = str(candidate.get("path", "")).strip().lower()
    stem = Path(title).stem.lower() if title else ""
    preview = str(candidate.get("preview", "")).strip().lower()
    suffix = Path(path or title).suffix.lower()
    score = 0.0

    if normalized_query in title:
        score += 8.0
    if normalized_query in stem:
        score += 6.0
    if normalized_query in path:
        score += 4.0
    if normalized_query in preview:
        score += 5.0

    tokens = [
        token
        for token in re.split(r"[^a-z0-9가-힣]+", normalized_query)
        if len(token) >= 2 and token not in {"project", "the", "about", "관련", "설명"}
    ]
    for token in tokens:
        if token in title:
            score += 2.0
        if token in stem:
            score += 1.5
        if token in path:
            score += 1.0
        if token in preview:
            score += 1.0

    markup_heavy = preview.startswith("<!doctype html") or preview.startswith("<html") or preview.count("<") >= 4
    has_name_match = normalized_query in title or normalized_query in stem or normalized_query in path
    if suffix in {".html", ".htm"} and markup_heavy and not has_name_match:
        score -= 6.0

    return score


def _select_topic_summary_candidates(topic_query: str) -> list[dict[str, object]]:
    ranked_by_path: dict[str, tuple[float, dict[str, object]]] = {}
    for variant in _topic_summary_query_variants(topic_query):
        candidates = _search_knowledge_base_topic_sources(variant, limit=12)
        for candidate in candidates:
            topical_score = _topic_candidate_score(variant, candidate)
            if topical_score <= 0:
                continue
            candidate_key = str(candidate.get("full_path", "")).strip() or str(candidate.get("path", "")).strip()
            if not candidate_key:
                continue
            existing = ranked_by_path.get(candidate_key)
            if existing is None or topical_score > existing[0]:
                ranked_by_path[candidate_key] = (topical_score, candidate)
    ranked = list(ranked_by_path.values())
    ranked.sort(
        key=lambda item: (
            item[0],
            float(item[1].get("score", 0.0) or 0.0),
            str(item[1].get("label", "")).lower(),
        ),
        reverse=True,
    )
    return [candidate for _, candidate in ranked[:4]]


def _topic_target_priority(target: dict[str, object]) -> tuple[int, str]:
    title = str(target.get("title", "")).strip().lower()
    path = str(target.get("path", "")).strip().lower()
    stem = Path(title or path).stem.lower()
    suffix = Path(path or title).suffix.lower()
    if stem == "readme":
        return (0, title)
    if suffix in {".md", ".txt", ".docx", ".pdf", ".html", ".htm"}:
        return (1, title)
    if suffix in {".pptx"}:
        return (2, title)
    return (3, title)


def _build_single_target_exploration(*, label: str, path: str, preview: str, kind: str) -> dict[str, object]:
    interaction_mode = "document_exploration" if kind == "document" else "source_exploration"
    candidate = {
        "label": label,
        "kind": kind,
        "path": path,
        "score": 1.0,
        "preview": preview,
    }
    return {
        "mode": interaction_mode,
        "target_file": label if kind != "document" else "",
        "target_document": label if kind == "document" else "",
        "file_candidates": [candidate] if kind != "document" else [],
        "document_candidates": [candidate] if kind == "document" else [],
        "class_candidates": [],
        "function_candidates": [],
    }


def _build_exploration_from_targets(targets: list[dict[str, object]]) -> dict[str, object]:
    exploration = {
        "mode": "document_exploration",
        "target_file": "",
        "target_document": "",
        "file_candidates": [],
        "document_candidates": [],
        "class_candidates": [],
        "function_candidates": [],
    }
    for target in targets:
        candidate = {
            "label": str(target.get("title", "")).strip(),
            "kind": str(target.get("kind", "")).strip() or "document",
            "path": str(target.get("path", "")).strip(),
            "score": float(target.get("score", 1.0) or 1.0),
            "preview": str(target.get("preview", "")).strip(),
        }
        if candidate["kind"] == "document":
            exploration["document_candidates"].append(candidate)
        else:
            exploration["file_candidates"].append(candidate)
    if len(targets) == 1:
        target = targets[0]
        if str(target.get("kind", "")).strip() == "document":
            exploration["target_document"] = str(target.get("title", "")).strip()
        else:
            exploration["target_file"] = str(target.get("title", "")).strip()
    return exploration


def _suggest_document_task_targets(session_id: str, lookup_query: str = "") -> list[dict[str, object]]:
    suggestions: list[dict[str, object]] = []
    if lookup_query:
        for item in _search_knowledge_base_documents(lookup_query):
            suggestions.append(
                _normalize_document_target(
                    {
                        "title": item["label"],
                        "path": item["path"],
                        "full_path": item["full_path"],
                        "preview": item["preview"],
                        "kind": "document",
                    }
                )
            )
    for target in _iter_session_document_targets(session_id):
        if any(
            str(existing.get("full_path", "")).strip() == str(target.get("full_path", "")).strip()
            for existing in suggestions
        ):
            continue
        suggestions.append(target)
    recent_target = _resolve_recent_document_target()
    if recent_target is not None and not any(
        str(existing.get("full_path", "")).strip() == str(recent_target.get("full_path", "")).strip()
        for existing in suggestions
    ):
        suggestions.append(_normalize_document_target(recent_target))
    return suggestions[:4]


def _build_document_task_clarification_payload(
    *,
    query: str,
    task_id: str,
    skill: str,
    prompt: str,
    session_id: str,
    lookup_query: str = "",
) -> dict[str, object]:
    suggestions = _suggest_document_task_targets(session_id, lookup_query)
    exploration = _build_exploration_from_targets(suggestions)
    suggested_replies = [str(item.get("title", "")).strip() for item in suggestions if str(item.get("title", "")).strip()]
    return {
        "query": query,
        "response": prompt,
        "spoken_response": prompt,
        "has_evidence": False,
        "citations": [],
        "status": _builtin_status_payload(),
        "render_hints": {
            "response_type": "builtin_answer",
            "primary_source_type": "document",
            "source_profile": task_id,
            "interaction_mode": "document_exploration",
            "citation_count": 0,
            "truncated": False,
        },
        "exploration": exploration,
        "guide_directive": {
            "intent": task_id,
            "skill": skill,
            "loop_stage": "waiting_user_reply",
            "clarification_prompt": prompt,
            "missing_slots": ["target_document"],
            "suggested_replies": suggested_replies[:4],
            "should_hold": True,
        },
        "answer_kind": "retrieval_result",
        "task_id": task_id,
        "structured_payload": {
            "candidate_count": len(suggestions),
            "lookup_query": lookup_query,
        },
        "ui_hints": {
            "show_documents": bool(suggestions),
            "show_repository": bool(suggestions),
            "show_inspector": False,
            "preferred_view": "repository" if suggestions else "dashboard",
        },
    }


def _strip_document_task_query(query: str) -> str:
    cleaned = re.sub(
        r"\b(summary|summarize|outline|headings?|table\s+of\s+contents|open|show|document|file|sheet|page|slide|contents?|overview|overall|structure|architecture)\b",
        " ",
        query,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(
        r"(요약|정리|개요|핵심|목차|아웃라인|헤딩|구성|슬라이드\s*제목|문서|파일|자료|이\s*문서|이\s*파일|열어\s*줘|열어줘|열기|열어|보여\s*줘|보여줘|알려\s*줘|알려줘|정리해\s*줘|정리해줘|요약해\s*줘|요약해줘|설명해\s*줘|설명해줘|설명|소개|종합(?:해서)?|개괄|전체|구조|아키텍처|흐름|관련(?:해서)?|에\s*대해|대해|해줘|다시|좀|한번|확인해줘|에서|시트|탭|슬라이드|페이지|내용|\d+\s*(?:번째\s*)?(?:슬라이드|페이지|시트|탭)|(?:슬라이드|페이지|시트|탭)\s*\d+|다음|이전|next|previous|prev)",
        " ",
        cleaned,
        flags=re.IGNORECASE,
    )
    return " ".join(cleaned.split()).strip(" ?.")


_GENERIC_DOCUMENT_TARGETS = {
    "이 문서",
    "이 파일",
    "이 자료",
    "그 문서",
    "그 파일",
    "그 자료",
    "저 문서",
    "저 파일",
    "저 자료",
    "문서",
    "파일",
    "자료",
}

_TOPIC_SUMMARY_DESCRIPTOR_RE = re.compile(
    r"(?:의\s*)?(?:기술\s*사양|사양|아키텍처|구조|흐름|개요|설명|소개|기능|관련\s*자료|관련\s*문서|문서|자료|specs?|specification|architecture|overview|structure|design|features?)\s*$",
    re.IGNORECASE,
)


def _topic_summary_query_variants(topic_query: str) -> tuple[str, ...]:
    normalized = " ".join(str(topic_query or "").split()).strip(" ?.!\"'`")
    if not normalized:
        return ()

    variants: list[str] = []
    seen: set[str] = set()

    def add(candidate: str) -> None:
        cleaned = " ".join(str(candidate or "").split()).strip(" ?.!\"'`")
        if not cleaned:
            return
        lowered = cleaned.lower()
        if lowered in seen:
            return
        seen.add(lowered)
        variants.append(cleaned)

    add(normalized)
    add(_TOPIC_SUMMARY_DESCRIPTOR_RE.sub("", normalized))

    if "의 " in normalized:
        add(normalized.split("의", 1)[0])

    return tuple(variants)


def _primary_topic_summary_query(topic_query: str) -> str:
    variants = _topic_summary_query_variants(topic_query)
    if not variants:
        return ""
    for candidate in variants[1:]:
        if candidate:
            return candidate
    return variants[0]


def _extract_explicit_document_target_query(query: str) -> str:
    normalized = " ".join(query.split()).strip()
    if not normalized:
        return ""
    patterns = (
        re.compile(r"^\s*(?P<target>.+?)\s*(?:에서|에\s*대해|관련(?:해서)?|기준으로)\b", re.IGNORECASE),
        re.compile(r"^\s*(?P<target>.+?)\s*(?:요약|정리|개요|목차|아웃라인|구조|설명|소개|종합(?:해서)?|개괄)\b", re.IGNORECASE),
    )
    for pattern in patterns:
        match = pattern.search(normalized)
        if match is None:
            continue
        candidate = " ".join(str(match.group("target") or "").split()).strip(" ?.!\"'`")
        if not candidate:
            continue
        if candidate.lower() in {value.lower() for value in _GENERIC_DOCUMENT_TARGETS}:
            return ""
        return candidate
    return ""


def _first_exploration_candidate(exploration: dict[str, object]) -> dict[str, object] | None:
    for group_name, kind in (("document_candidates", "document"), ("file_candidates", "filename")):
        for item in exploration.get(group_name, []):
            if not isinstance(item, dict):
                continue
            relative_path = str(item.get("path", "")).strip()
            if not relative_path:
                continue
            full_path = _resolve_full_path(relative_path, relative_path)
            if not full_path:
                continue
            return {
                "title": str(item.get("label", "")).strip() or Path(full_path).name,
                "path": relative_path,
                "full_path": full_path,
                "preview": str(item.get("preview", "")).strip(),
                "kind": kind,
                "exploration": exploration,
            }
    return None


def _collect_exploration_candidates(exploration: dict[str, object]) -> list[dict[str, object]]:
    candidates: list[dict[str, object]] = []
    for group_name, kind in (("document_candidates", "document"), ("file_candidates", "filename")):
        for item in exploration.get(group_name, []):
            if not isinstance(item, dict):
                continue
            relative_path = str(item.get("path", "")).strip()
            if not relative_path:
                continue
            full_path = _resolve_full_path(relative_path, relative_path)
            if not full_path:
                continue
            candidates.append(
                {
                    "title": str(item.get("label", "")).strip() or Path(full_path).name,
                    "path": relative_path,
                    "full_path": full_path,
                    "preview": str(item.get("preview", "")).strip(),
                    "kind": kind,
                    "score": float(item.get("score", 0.0) or 0.0),
                    "exploration": exploration,
                }
            )
    return candidates


def _resolve_recent_document_target() -> dict[str, object] | None:
    for context in _iter_recent_runtime_contexts():
        orchestrator = getattr(context, "orchestrator", None)
        answer = getattr(orchestrator, "last_answer", None)
        if answer is None or not getattr(answer.evidence, "items", ()):
            continue
        top_item = answer.evidence.items[0]
        full_path = str(getattr(top_item, "source_path", "") or "").strip()
        if not full_path:
            continue
        title = Path(full_path).name
        preview = str(getattr(top_item, "text", "") or "").strip()
        interaction_kind = "document" if Path(full_path).suffix.lower() in {".md", ".txt", ".pdf", ".docx", ".pptx", ".xlsx", ".csv", ".tsv", ".hwp", ".hwpx", ".html", ".htm"} else "filename"
        return {
            "title": title,
            "path": full_path,
            "full_path": full_path,
            "preview": preview,
            "kind": interaction_kind,
            "exploration": _build_single_target_exploration(
                label=title,
                path=full_path,
                preview=preview,
                kind=interaction_kind,
            ),
        }
    return None


def _document_target_match_score(target: dict[str, object], lookup_query: str) -> int:
    normalized_query = lookup_query.strip().lower()
    if not normalized_query:
        return 0
    title = str(target.get("title", "")).strip().lower()
    path = str(target.get("path", "")).strip().lower()
    stem = Path(path or title).stem.lower()
    score = 0
    for candidate in (title, path, stem):
        if not candidate:
            continue
        if candidate == normalized_query:
            score = max(score, 100)
        elif normalized_query in candidate:
            score = max(score, 60)
    tokens = [
        token
        for token in re.split(r"[^a-z0-9가-힣]+", normalized_query)
        if len(token) >= 2
    ]
    if not tokens:
        return score
    token_hits = 0
    for token in tokens:
        if any(token in candidate for candidate in (title, path, stem)):
            token_hits += 1
    return score + token_hits * 10


def _resolve_document_task_target_from_lookup(
    lookup_query: str,
    *,
    session_id: str = "",
) -> dict[str, object] | None:
    if lookup_query:
        exploration = asdict(_build_navigation_window(query=lookup_query, model_id="menu-bar-rpc"))
        candidates = _collect_exploration_candidates(exploration)
        if candidates:
            exact_matches = [
                candidate
                for candidate in candidates
                if _document_target_match_score(candidate, lookup_query) >= 100
            ]
            if len(exact_matches) == 1:
                return exact_matches[0]
            session_targets = _iter_session_document_targets(session_id)
            for session_target in session_targets:
                session_path = str(session_target.get("full_path", "")).strip()
                if not session_path:
                    continue
                matching_candidate = next(
                    (
                        candidate
                        for candidate in candidates
                        if str(candidate.get("full_path", "")).strip() == session_path
                    ),
                    None,
                )
                if matching_candidate is not None and _document_target_match_score(
                    matching_candidate,
                    lookup_query,
                ) >= 10:
                    return matching_candidate
            return candidates[0]

        fallback_candidates = _search_knowledge_base_documents(lookup_query)
        if fallback_candidates:
            selected = fallback_candidates[0]
            return {
                "title": str(selected["label"]),
                "path": str(selected["path"]),
                "full_path": str(selected["full_path"]),
                "preview": str(selected["preview"]),
                "kind": "document",
                "exploration": {
                    "mode": "document_exploration",
                    "target_file": "",
                    "target_document": str(selected["label"]),
                    "file_candidates": [],
                    "document_candidates": [
                        {
                            "label": str(item["label"]),
                            "kind": "document",
                            "path": str(item["path"]),
                            "score": float(item["score"]),
                            "preview": str(item["preview"]),
                        }
                        for item in fallback_candidates
                    ],
                    "class_candidates": [],
                    "function_candidates": [],
                },
            }

    session_targets = _iter_session_document_targets(session_id)
    if session_targets:
        return session_targets[0]
    return _resolve_recent_document_target()


def _resolve_document_task_target(query: str, session_id: str = "") -> dict[str, object] | None:
    lookup_query = _extract_explicit_document_target_query(query) or _strip_document_task_query(query)
    return _resolve_document_task_target_from_lookup(lookup_query, session_id=session_id)


def _load_document_task_content(full_path: str) -> dict[str, object]:
    path = Path(full_path)
    parsed_doc = _document_parser.parse_structured(path)
    raw_text = ""
    try:
        raw_text = parsed_doc.to_text()
    except Exception:
        raw_text = ""
    if not raw_text.strip():
        raw_text = _document_parser.parse(path)
    return {
        "path": path,
        "format": str(parsed_doc.metadata.get("format", path.suffix.lower().lstrip(".")) or ""),
        "elements": list(parsed_doc.elements),
        "text": raw_text,
    }


_CODE_DOCUMENT_FORMATS = {
    "python",
    "typescript",
    "javascript",
    "code",
    "c",
    "cpp",
    "go",
    "rust",
    "java",
    "swift",
    "kotlin",
}


def _ordered_unique(values: list[str]) -> list[str]:
    ordered: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = str(value).strip()
        if not normalized or normalized in seen:
            continue
        ordered.append(normalized)
        seen.add(normalized)
    return ordered


def _document_code_language(document: dict[str, object]) -> str:
    for element in document.get("elements") or []:
        if getattr(element, "element_type", "") != "code":
            continue
        metadata = getattr(element, "metadata", {}) or {}
        language = str(metadata.get("language", "")).strip()
        if language:
            return language
    return str(document.get("format", "") or "").strip()


def _is_code_document(document: dict[str, object]) -> bool:
    doc_format = str(document.get("format", "") or "").strip().lower()
    if doc_format in _CODE_DOCUMENT_FORMATS:
        return True
    return any(getattr(element, "element_type", "") == "code" for element in document.get("elements") or [])


def _extract_code_symbols(document: dict[str, object]) -> dict[str, object]:
    text = str(document.get("text", "") or "")
    language = _document_code_language(document).lower()
    imports: list[str] = []
    classes: list[str] = []
    functions: list[str] = []

    if not text.strip():
        return {"language": language, "imports": imports, "classes": classes, "functions": functions}

    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()
        if not stripped:
            continue
        if language == "python":
            if re.match(r"^\s*(?:from\s+\S+\s+import\s+.+|import\s+.+)$", line):
                imports.append(stripped)
            match = re.match(r"^\s*class\s+([A-Za-z_]\w*)", line)
            if match:
                classes.append(str(match.group(1)))
            match = re.match(r"^\s*(?:async\s+def|def)\s+([A-Za-z_]\w*)", line)
            if match:
                functions.append(str(match.group(1)))
            continue

        if re.match(r"^\s*(?:import\s.+|(?:const|let|var)\s+\w+\s*=\s*require\s*\()", line):
            imports.append(stripped)
        match = re.match(r"^\s*(?:export\s+)?class\s+([A-Za-z_$][\w$]*)", line)
        if match:
            classes.append(str(match.group(1)))
        function_patterns = (
            re.compile(r"^\s*(?:export\s+)?function\s+([A-Za-z_$][\w$]*)"),
            re.compile(r"^\s*(?:export\s+)?const\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?\("),
            re.compile(r"^\s*(?:export\s+)?async\s+function\s+([A-Za-z_$][\w$]*)"),
        )
        for pattern in function_patterns:
            match = pattern.match(line)
            if match:
                functions.append(str(match.group(1)))
                break

    return {
        "language": language,
        "imports": _ordered_unique(imports),
        "classes": _ordered_unique(classes),
        "functions": _ordered_unique(functions),
    }


def _extract_outline_entries(document: dict[str, object]) -> list[str]:
    text = str(document.get("text", "") or "")
    elements = document.get("elements") or []
    doc_format = str(document.get("format", "") or "")

    if _is_code_document(document):
        code_symbols = _extract_code_symbols(document)
        entries: list[str] = []
        if code_symbols["imports"]:
            entries.append(f"imports ({len(code_symbols['imports'])})")
        entries.extend(f"class {name}" for name in code_symbols["classes"][:6])
        function_prefix = "def" if code_symbols["language"] == "python" else "function"
        entries.extend(f"{function_prefix} {name}" for name in code_symbols["functions"][:8])
        return entries

    if doc_format == "xlsx":
        entries: list[str] = []
        for element in elements:
            metadata = getattr(element, "metadata", {}) or {}
            sheet_name = str(metadata.get("sheet_name", "")).strip() or "Sheet"
            headers = metadata.get("headers") or ()
            rows = metadata.get("rows") or ()
            entries.append(f"{sheet_name} · 컬럼 {len(headers)}개 · 행 {len(rows)}개")
        return entries

    if "[Slide " in text:
        entries = []
        current_slide = ""
        slide_lines: list[str] = []
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            if line.startswith("[Slide "):
                if current_slide and slide_lines:
                    entries.append(f"{current_slide} · {slide_lines[0]}")
                current_slide = line.strip("[]")
                slide_lines = []
                continue
            if line.startswith("[Notes]"):
                continue
            slide_lines.append(line)
        if current_slide and slide_lines:
            entries.append(f"{current_slide} · {slide_lines[0]}")
        return entries

    entries = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if re.match(r"^#{1,6}\s+", line):
            entries.append(re.sub(r"^#{1,6}\s+", "", line))
            continue
        if re.match(r"^\d+(?:\.\d+)*[\.)]?\s+\S+", line):
            entries.append(line)
            continue
        if len(line) <= 80 and line == line.upper() and re.search(r"[A-Z가-힣]", line):
            entries.append(line.title() if line.isupper() else line)
    deduped: list[str] = []
    seen: set[str] = set()
    for entry in entries:
        normalized = entry.strip()
        if not normalized or normalized in seen:
            continue
        deduped.append(normalized)
        seen.add(normalized)
    return deduped


def _extract_summary_lines(document: dict[str, object], outline: list[str]) -> list[str]:
    path = document["path"]
    doc_format = str(document.get("format", "") or "")
    elements = document.get("elements") or []
    text = str(document.get("text", "") or "")

    summary_lines: list[str] = []
    if _is_code_document(document):
        code_symbols = _extract_code_symbols(document)
        language = str(code_symbols["language"] or doc_format or "code").strip()
        summary_lines.append(f"{path.name}는 {language} 코드 파일입니다.")
        composition: list[str] = []
        if code_symbols["imports"]:
            composition.append(f"import {len(code_symbols['imports'])}개")
        if code_symbols["classes"]:
            composition.append(f"class {len(code_symbols['classes'])}개")
        if code_symbols["functions"]:
            composition.append(f"함수 {len(code_symbols['functions'])}개")
        if composition:
            summary_lines.append(f"{', '.join(composition)}로 구성됩니다.")
        if code_symbols["classes"]:
            summary_lines.append(f"주요 클래스는 {', '.join(code_symbols['classes'][:4])}입니다.")
        if code_symbols["functions"]:
            summary_lines.append(f"주요 함수는 {', '.join(code_symbols['functions'][:5])}입니다.")
        if len(summary_lines) > 1:
            return summary_lines[:6]
        code_lines = [
            raw_line.strip()
            for raw_line in text.splitlines()
            if raw_line.strip() and len(raw_line.strip()) >= 8
        ]
        summary_lines.extend(code_lines[:4])
        return summary_lines[:6]

    if doc_format == "xlsx":
        for element in elements[:4]:
            metadata = getattr(element, "metadata", {}) or {}
            sheet_name = str(metadata.get("sheet_name", "")).strip() or "Sheet"
            headers = metadata.get("headers") or ()
            rows = metadata.get("rows") or ()
            header_preview = ", ".join(str(header).strip() for header in headers[:4] if str(header).strip())
            line = f"{sheet_name} 시트에 행 {len(rows)}개, 컬럼 {len(headers)}개가 있습니다."
            if header_preview:
                line += f" 주요 컬럼은 {header_preview}입니다."
            summary_lines.append(line)
        return summary_lines

    if "[Slide " in text:
        slide_entries = outline[:4]
        if slide_entries:
            summary_lines.append(f"총 {len(outline)}개 슬라이드로 구성됩니다.")
            summary_lines.extend(slide_entries)
            return summary_lines

    if outline:
        summary_lines.append(f"주요 섹션은 {', '.join(outline[:3])}입니다.")

    paragraphs: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or line.startswith("[Slide "):
            continue
        if len(line) < 20:
            continue
        if "|" in line and doc_format in {"docx", "text", "markdown"}:
            continue
        paragraphs.append(line)

    for paragraph in paragraphs[:4]:
        summary_lines.append(paragraph[:220])

    if not summary_lines:
        summary_lines.append(f"{path.name} 문서를 열었지만 요약 가능한 텍스트가 충분하지 않습니다.")
    return summary_lines[:6]


def _extract_topic_document_highlight(
    document: dict[str, object],
    *,
    fallback_preview: str = "",
) -> str:
    text = str(document.get("text", "") or "")
    code_comment_highlight = _extract_code_comment_highlight(document)
    if code_comment_highlight:
        return code_comment_highlight
    if "[Slide " in text:
        first_slide_lines: list[str] = []
        current_slide = 0
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            if line.startswith("[Slide "):
                if current_slide == 1 and first_slide_lines:
                    break
                slide_match = re.search(r"\[Slide\s+(\d+)\]", line, re.IGNORECASE)
                current_slide = int(slide_match.group(1)) if slide_match else 0
                continue
            if line.startswith("[Notes]"):
                continue
            if current_slide in {0, 1}:
                first_slide_lines.append(line)
        highlight = " ".join(first_slide_lines[:6]).strip()
        if highlight:
            return highlight[:220]

    summary_lines = _extract_summary_lines(document, _extract_outline_entries(document))
    for line in summary_lines:
        normalized = str(line).strip()
        if not normalized:
            continue
        if re.match(r"^총\s+\d+개\s+슬라이드", normalized):
            continue
        if re.match(r"^Slide\s+\d+\s+·", normalized, re.IGNORECASE):
            continue
        if normalized.startswith("주요 섹션은 ") and len(summary_lines) > 1:
            continue
        return normalized[:220]

    preview_lines = [
        line.strip()
        for line in str(fallback_preview or "").splitlines()
        if line.strip() and not line.strip().startswith("[Slide ") and not line.strip().startswith("[Notes]")
    ]
    if preview_lines:
        return " ".join(preview_lines[:5])[:220]
    return ""


def _clean_topic_highlight(topic_title: str, highlight: str) -> str:
    cleaned = " ".join(str(highlight or "").split()).strip()
    if not cleaned:
        return ""
    cleaned = re.sub(r"^[A-Z][A-Z0-9 .:_/-]{8,}\s+", "", cleaned)
    topic_pattern = re.escape(str(topic_title or "").strip())
    if topic_pattern:
        cleaned = re.sub(
            rf"^\s*{topic_pattern}\s*(?:는|은|를|가)?\s*",
            "",
            cleaned,
            flags=re.IGNORECASE,
        ).strip()
    cleaned = cleaned.lstrip(":,- ").strip()
    return cleaned[:220]


def _compose_topic_summary_lines(
    topic_title: str,
    highlights: list[tuple[str, str]],
) -> list[str]:
    cleaned_highlights: list[tuple[str, str]] = []
    for title, highlight in highlights:
        cleaned = _clean_topic_highlight(topic_title, highlight)
        if not cleaned:
            continue
        if any(existing_highlight == cleaned for _, existing_highlight in cleaned_highlights):
            continue
        cleaned_highlights.append((title, cleaned))

    if not cleaned_highlights:
        return []

    non_code_highlights = [
        (title, cleaned)
        for title, cleaned in cleaned_highlights
        if Path(title).suffix.lower() not in _TOPIC_SOURCE_EXTENSIONS - _DOCUMENT_EXTENSIONS
    ]
    code_highlights = [
        (title, cleaned)
        for title, cleaned in cleaned_highlights
        if Path(title).suffix.lower() in _TOPIC_SOURCE_EXTENSIONS - _DOCUMENT_EXTENSIONS
    ]

    overall_parts: list[str] = []
    source_for_overview = non_code_highlights or cleaned_highlights
    for _, cleaned in source_for_overview[:2]:
        overall_parts.append(cleaned.rstrip("."))

    summary_lines = [f"{topic_title}는 {' '.join(overall_parts)}.".strip()]
    if code_highlights:
        code_modules = ", ".join(Path(title).stem for title, _ in code_highlights[:3])
        summary_lines.append(
            f"코드 자료에는 {code_modules} 같은 구성요소가 포함돼 있어 앱 구조와 구현 기능을 함께 확인할 수 있습니다."
        )
    for title, cleaned in cleaned_highlights[:3]:
        summary_lines.append(f"{title} 기준 {cleaned}")
    return summary_lines


_TOPIC_HTML_TAG_RE = re.compile(r"<[^>]+>")
_JAPANESE_KANA_RE = re.compile(r"[\u3040-\u30ff]+")
_JAPANESE_TERM_REPLACEMENTS = {
    "스ムーズ": "원활한",
    "スムーズ": "원활한",
    "스ムース": "원활한",
    "スムース": "원활한",
    "시ームレス": "매끄럽게 연결되는",
    "シームレス": "매끄럽게 연결되는",
    "ユーザー": "사용자",
    "データ": "데이터",
    "ネットワーク": "네트워크",
    "プラットフォーム": "플랫폼",
    "システム": "시스템",
    "プロセス": "프로세스",
    "サポート": "지원",
    "ワークフロー": "워크플로우",
}


def _extract_code_comment_highlight(document: dict[str, object]) -> str:
    if not _is_code_document(document):
        return ""
    text = str(document.get("text", "") or "")
    comment_lines: list[str] = []
    for raw_line in text.splitlines()[:24]:
        stripped = raw_line.strip()
        if not stripped:
            if comment_lines:
                break
            continue
        if stripped.startswith("//"):
            comment = stripped[2:].strip(" */\t")
        elif stripped.startswith("#"):
            comment = stripped[1:].strip(" */\t")
        elif stripped.startswith("/*") or stripped.startswith("*"):
            comment = stripped.lstrip("/*").strip(" */\t")
        else:
            break
        if not comment:
            continue
        if comment.lower().endswith((".swift", ".py", ".ts", ".tsx", ".js", ".java", ".go", ".rs")):
            continue
        if re.fullmatch(r"ProjectHub", comment, re.IGNORECASE):
            continue
        comment_lines.append(comment)
    if not comment_lines:
        return ""
    return " ".join(comment_lines[:4])[:260]


def _sanitize_topic_evidence_text(text: str) -> str:
    cleaned = html.unescape(str(text or ""))
    cleaned = _TOPIC_HTML_TAG_RE.sub(" ", cleaned)
    cleaned = re.sub(r"charset\s*=\s*[A-Za-z0-9._-]+", " ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip()


def _normalize_topic_summary_language(text: str) -> str:
    cleaned = str(text or "")
    for source, target in sorted(_JAPANESE_TERM_REPLACEMENTS.items(), key=lambda item: len(item[0]), reverse=True):
        cleaned = cleaned.replace(source, target)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip()


def _contains_japanese_kana(text: str) -> bool:
    return bool(_JAPANESE_KANA_RE.search(str(text or "")))


def _build_topic_evidence_text(target: dict[str, object], document: dict[str, object]) -> str:
    title = str(target.get("title", "")).strip() or str(document.get("path", ""))
    outline = _extract_outline_entries(document)
    summary_lines = _extract_summary_lines(document, outline)
    parts: list[str] = []
    highlight = _extract_topic_document_highlight(
        document,
        fallback_preview=str(target.get("preview", "")).strip(),
    )
    if highlight:
        normalized_highlight = _sanitize_topic_evidence_text(highlight)
        if normalized_highlight:
            parts.append(normalized_highlight)
    for line in summary_lines[:4]:
        normalized = _sanitize_topic_evidence_text(str(line))
        if not normalized:
            continue
        if normalized.lower().startswith("slide ") or normalized.startswith("총 "):
            continue
        if normalized in parts:
            continue
        parts.append(normalized)
    if not parts:
        preview = _sanitize_topic_evidence_text(str(target.get("preview", "")).strip())
        if preview:
            parts.append(preview)
    if not parts:
        return ""
    return f"{title}: " + " ".join(parts[:3])


def _topic_summary_model_candidates() -> tuple[str, ...]:
    ordered: list[str] = []
    seen: set[str] = set()
    for model in (*_menu_bar_model_chain(), *_PREFERRED_LOCAL_MODELS):
        normalized = str(model).strip()
        if not normalized or normalized.lower() == "stub" or normalized in seen:
            continue
        ordered.append(normalized)
        seen.add(normalized)
    return tuple(ordered)


def _generate_topic_summary_with_llm(
    *,
    query: str,
    topic_title: str,
    targets: list[dict[str, object]],
    fallback_summary_lines: list[str],
) -> dict[str, object] | None:
    model_candidates = _topic_summary_model_candidates()
    if not model_candidates:
        return None

    evidence_items: list[EvidenceItem] = []
    for index, target in enumerate(targets, start=1):
        document = _load_document_task_content(str(target["full_path"]))
        evidence_text = _build_topic_evidence_text(target, document)
        if not evidence_text:
            continue
        full_path = str(target.get("full_path", "")).strip()
        chunk_id = f"topic-summary-{index}"
        evidence_items.append(
            EvidenceItem(
                chunk_id=chunk_id,
                document_id=full_path,
                text=evidence_text,
                citation=CitationRecord(
                    document_id=full_path,
                    chunk_id=chunk_id,
                    label=f"[{index}]",
                    state=CitationState.VALID,
                ),
                relevance_score=max(0.85 - (index - 1) * 0.1, 0.45),
                source_path=full_path,
                heading_path=str(target.get("title", "")).strip(),
            )
        )

    if not evidence_items:
        return None

    evidence = VerifiedEvidenceSet(
        items=tuple(evidence_items),
        query_fragments=(TypedQueryFragment(text=topic_title, language="ko", query_type="semantic", weight=1.0),),
    )
    prompt = (
        f"주제: {topic_title}\n"
        f"사용자 질문: {query}\n"
        "아래 근거 자료들을 종합해 제품이나 주제를 자연스러운 한국어로 3~5문장으로 설명하세요.\n"
        "- 답변은 한국어와 필요한 영문 고유명사만 사용하세요.\n"
        "- 일본어(히라가나/가타카나) 표현은 절대 사용하지 마세요.\n"
        "- 파일명, HTML 태그, 메타 태그를 그대로 답에 넣지 마세요.\n"
        "- 자료들에 공통으로 드러나는 목적, 핵심 기능, 사용 맥락을 먼저 설명하세요.\n"
        "- 근거에 없는 추측은 하지 마세요.\n"
        "- 목록 나열보다 종합 설명을 우선하세요.\n"
    )

    last_error: Exception | None = None
    for model_id in model_candidates:
        try:
            context = _get_runtime_context(model_id=model_id)
            orchestrator = getattr(context, "orchestrator", None)
            error_monitor = getattr(context, "error_monitor", None)
            if orchestrator is None:
                continue
            answer = orchestrator._generate_answer(prompt, evidence, recent_turns=None)
            answer = orchestrator._apply_post_generation_guard(answer, evidence=evidence)
            normalized_content = _normalize_topic_summary_language(answer.content)
            if _contains_japanese_kana(normalized_content):
                continue
            if normalized_content != answer.content:
                answer = AnswerDraft(
                    content=normalized_content,
                    evidence=answer.evidence,
                    model_id=answer.model_id,
                    verification_warnings=answer.verification_warnings,
                )
            if answer.model_id in {"abstain", "clarify", "stub"} or not answer.content.strip():
                continue
            response = build_menu_response(
                turn=ConversationTurn(
                    user_input=query,
                    assistant_output=answer.content,
                    has_evidence=bool(answer.evidence.items),
                ),
                answer=answer,
                safe_mode=bool(error_monitor.safe_mode_active()) if error_monitor is not None else False,
                degraded_mode=bool(getattr(error_monitor, "degraded_mode", False)),
                generation_blocked=bool(getattr(error_monitor, "generation_blocked", False)),
                write_blocked=bool(getattr(error_monitor, "write_blocked", False)),
                rebuild_index_required=bool(getattr(error_monitor, "rebuild_index_required", False)),
                knowledge_base_path=getattr(context, "knowledge_base_path", None),
                planner_analysis=None,
            )
            payload = asdict(response)
            payload["answer_kind"] = "retrieval_result"
            payload["task_id"] = "doc_summary"
            payload["structured_payload"] = {
                "title": topic_title,
                "format": "multi_document",
                "summary_lines": fallback_summary_lines,
                "outline": [],
                "source_titles": [
                    str(target.get("title", "")).strip()
                    for target in targets
                    if str(target.get("title", "")).strip()
                ],
                "source_count": len(targets),
                "ai_synthesized": True,
                "model_id": answer.model_id,
            }
            payload["ui_hints"] = {
                "show_documents": True,
                "show_repository": True,
                "show_inspector": bool(payload.get("citations")),
                "preferred_view": "dashboard",
            }
            if payload.get("guide_directive") is None:
                payload["guide_directive"] = {}
            payload["guide_directive"]["suggested_replies"] = [
                f"{str(target.get('title', '')).strip()} 열어줘"
                for target in targets[:3]
                if str(target.get("title", "")).strip()
            ]
            return payload
        except Exception as exc:
            last_error = exc
            continue
    return None


def _extract_sheet_entries(document: dict[str, object]) -> list[dict[str, object]]:
    entries: list[dict[str, object]] = []
    for element in document.get("elements") or []:
        metadata = getattr(element, "metadata", {}) or {}
        sheet_name = str(metadata.get("sheet_name", "")).strip()
        if not sheet_name:
            continue
        headers = metadata.get("headers") or ()
        rows = metadata.get("rows") or ()
        entries.append({
            "sheet_name": sheet_name,
            "column_count": len(headers),
            "row_count": len(rows),
            "header_preview": ", ".join(str(header).strip() for header in headers[:4] if str(header).strip()),
            "headers": [str(header).strip() for header in headers if str(header).strip()],
            "first_row_preview": " | ".join(str(cell).strip() for cell in rows[0][:6] if str(cell).strip()) if rows else "",
        })
    return entries


def _strip_document_sheet_target_query(query: str) -> str:
    cleaned = re.sub(
        r"(?:[A-Za-z0-9가-힣._-]+\s*(?:시트|sheet|탭)|(?:시트|sheet|탭)\s*[A-Za-z0-9가-힣._-]+|\d+\s*(?:번째\s*)?(?:시트|sheet|탭)|(?:시트|sheet|탭)\s*\d+)",
        " ",
        query,
        flags=re.IGNORECASE,
    )
    return _strip_document_task_query(cleaned)


def _extract_requested_sheet_selector(query: str) -> dict[str, object] | None:
    normalized = " ".join(query.split()).strip()
    patterns = (
        re.compile(r"(?P<index>\d+)\s*(?:번째\s*)?(?:시트|sheet|탭)", re.IGNORECASE),
        re.compile(r"(?:시트|sheet|탭)\s*(?P<index>\d+)", re.IGNORECASE),
        re.compile(r"(?P<name>[A-Za-z0-9가-힣._-]+)\s*(?:시트|sheet|탭)", re.IGNORECASE),
        re.compile(r"(?:시트|sheet|탭)\s*(?P<name>[A-Za-z0-9가-힣._-]+)", re.IGNORECASE),
    )
    for pattern in patterns:
        match = pattern.search(normalized)
        if match is None:
            continue
        raw = match.group(0).strip()
        raw_index = match.groupdict().get("index", "") or ""
        if raw_index.isdigit():
            return {
                "kind": "index",
                "index": int(raw_index),
                "raw": raw,
            }
        raw_name = str(match.groupdict().get("name", "") or "").strip()
        if not raw_name:
            continue
        if raw_name.lower() in {"sheet", "시트", "탭", "list", "목록", "리스트"}:
            continue
        return {
            "kind": "name",
            "name": raw_name,
            "raw": raw,
        }
    return None


def _select_sheet_entry(
    sheets: list[dict[str, object]],
    selector: dict[str, object],
) -> tuple[int, dict[str, object]] | None:
    selector_kind = str(selector.get("kind", "")).strip()
    if selector_kind == "index":
        index = int(selector.get("index", 0) or 0)
        if 1 <= index <= len(sheets):
            return index, sheets[index - 1]
        return None
    requested_name = str(selector.get("name", "")).strip().lower()
    if not requested_name:
        return None
    for index, sheet in enumerate(sheets, start=1):
        sheet_name = str(sheet.get("sheet_name", "")).strip().lower()
        if sheet_name == requested_name:
            return index, sheet
    for index, sheet in enumerate(sheets, start=1):
        sheet_name = str(sheet.get("sheet_name", "")).strip().lower()
        if requested_name in sheet_name or sheet_name in requested_name:
            return index, sheet
    return None


def _extract_requested_document_section(query: str) -> tuple[str, int] | None:
    match = re.search(
        r"(?:(?P<kind>슬라이드|slide|페이지|page)\s*(?P<number>\d+)|(?P<number2>\d+)\s*(?:번째\s*)?(?P<kind2>슬라이드|slide|페이지|page))",
        query,
        re.IGNORECASE,
    )
    if match is None:
        return None
    raw_kind = (match.group("kind") or match.group("kind2") or "").strip().lower()
    raw_number = match.group("number") or match.group("number2") or ""
    if not raw_number.isdigit():
        return None
    kind = "slide" if raw_kind in {"슬라이드", "slide"} else "page"
    return kind, int(raw_number)


def _extract_relative_document_section(query: str) -> tuple[str | None, int] | None:
    match = re.search(
        r"(?:(?P<direction>다음|next|이전|previous|prev)\s*(?P<kind>슬라이드|slide|페이지|page)|(?P<kind2>슬라이드|slide|페이지|page)\s*(?P<direction2>다음|next|이전|previous|prev))",
        query,
        re.IGNORECASE,
    )
    if match is None:
        return None
    raw_direction = (match.group("direction") or match.group("direction2") or "").strip().lower()
    raw_kind = (match.group("kind") or match.group("kind2") or "").strip().lower()
    delta = 1 if raw_direction in {"다음", "next"} else -1
    kind = "slide" if raw_kind in {"슬라이드", "slide"} else "page"
    return kind, delta


def _extract_slide_section(document: dict[str, object], index: int) -> list[str]:
    text = str(document.get("text", "") or "")
    current_slide = 0
    collected: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("[Slide "):
            slide_match = re.search(r"\[Slide\s+(\d+)\]", line, re.IGNORECASE)
            current_slide = int(slide_match.group(1)) if slide_match else 0
            continue
        if current_slide != index:
            continue
        if line.startswith("[Notes]"):
            collected.append(line.replace("[Notes]", "Notes:", 1).strip())
            continue
        collected.append(line)
    return collected[:12]


def _extract_page_section(document: dict[str, object], index: int) -> list[str]:
    section_lines: list[str] = []
    for element in document.get("elements") or []:
        metadata = getattr(element, "metadata", {}) or {}
        if int(metadata.get("page", 0) or 0) != index:
            continue
        text = str(getattr(element, "text", "") or "").strip()
        if text:
            for line in text.splitlines():
                normalized = line.strip()
                if normalized:
                    section_lines.append(normalized)
        headers = metadata.get("headers") or ()
        rows = metadata.get("rows") or ()
        if headers or rows:
            preview = " | ".join(str(header).strip() for header in headers if str(header).strip())
            if preview:
                section_lines.append(preview)
            if rows:
                first_row = " | ".join(str(cell).strip() for cell in rows[0] if str(cell).strip())
                if first_row:
                    section_lines.append(first_row)
    deduped: list[str] = []
    seen: set[str] = set()
    for line in section_lines:
        normalized = line.strip()
        if not normalized or normalized in seen:
            continue
        deduped.append(normalized)
        seen.add(normalized)
    return deduped[:12]


def _build_document_task_payload(
    *,
    query: str,
    task_id: str,
    skill: str,
    response_text: str,
    target: dict[str, object],
    structured_payload: dict[str, object],
    suggested_replies: list[str] | None = None,
) -> dict[str, object]:
    exploration = target["exploration"]
    interaction_mode = str(exploration.get("mode", "")).strip() or "document_exploration"
    replies = [
        reply.strip()
        for reply in (suggested_replies or [
            f"{target['title']} 열어줘",
            f"{target['title']} 목차 보여줘" if task_id == "doc_summary" else f"{target['title']} 요약해줘",
        ])
        if str(reply).strip()
    ]
    return {
        "query": query,
        "response": response_text,
        "spoken_response": response_text,
        "has_evidence": False,
        "citations": [],
        "status": _builtin_status_payload(),
        "render_hints": {
            "response_type": "builtin_answer",
            "primary_source_type": "document" if interaction_mode == "document_exploration" else "code",
            "source_profile": task_id,
            "interaction_mode": interaction_mode,
            "citation_count": 0,
            "truncated": False,
        },
        "exploration": exploration,
        "guide_directive": {
            "intent": task_id,
            "skill": skill,
            "loop_stage": "presenting",
            "clarification_prompt": "",
            "missing_slots": [],
            "suggested_replies": replies,
            "should_hold": False,
        },
        "answer_kind": "retrieval_result",
        "task_id": task_id,
        "structured_payload": structured_payload,
        "ui_hints": {
            "show_documents": True,
            "show_repository": True,
            "show_inspector": False,
            "preferred_view": "detail_viewer",
        },
    }


def _build_topic_summary_payload(
    *,
    query: str,
    topic_title: str,
    targets: list[dict[str, object]],
    summary_lines: list[str],
) -> dict[str, object]:
    exploration = _build_exploration_from_targets(targets)
    if summary_lines:
        headline = str(summary_lines[0]).strip()
        detail_line = str(summary_lines[1]).strip() if len(summary_lines) >= 2 and " 기준 " not in str(summary_lines[1]) else ""
        response_text = " ".join(part for part in (headline, detail_line) if part).strip()
    else:
        response_text = f"{topic_title} 관련 자료 {len(targets)}개를 종합했습니다."
    suggested_replies = [
        f"{str(target.get('title', '')).strip()} 열어줘"
        for target in targets[:3]
        if str(target.get("title", "")).strip()
    ]
    return {
        "query": query,
        "response": response_text,
        "spoken_response": response_text,
        "has_evidence": False,
        "citations": [],
        "status": _builtin_status_payload(),
        "render_hints": {
            "response_type": "builtin_answer",
            "primary_source_type": "document",
            "source_profile": "doc_summary",
            "interaction_mode": "document_exploration",
            "citation_count": 0,
            "truncated": False,
        },
        "exploration": exploration,
        "guide_directive": {
            "intent": "doc_summary",
            "skill": "builtin_document_summary",
            "loop_stage": "presenting",
            "clarification_prompt": "",
            "missing_slots": [],
            "suggested_replies": suggested_replies,
            "should_hold": False,
        },
        "answer_kind": "retrieval_result",
        "task_id": "doc_summary",
        "structured_payload": {
            "title": topic_title,
            "format": "multi_document",
            "summary_lines": summary_lines,
            "outline": [],
            "source_titles": [
                str(target.get("title", "")).strip()
                for target in targets
                if str(target.get("title", "")).strip()
            ],
            "source_count": len(targets),
        },
        "ui_hints": {
            "show_documents": True,
            "show_repository": True,
            "show_inspector": False,
            "preferred_view": "dashboard",
        },
    }


def _resolve_document_sheet_list_payload(query: str, session_id: str = "") -> dict[str, object] | None:
    target = _resolve_document_task_target(query, session_id=session_id)
    if target is None:
        return _build_document_task_clarification_payload(
            query=query,
            task_id="sheet_list",
            skill="builtin_document_sheet_list",
            prompt="어느 스프레드시트의 시트 목록을 볼지 먼저 알려주세요.",
            session_id=session_id,
            lookup_query=_strip_document_task_query(query),
        )
    document = _load_document_task_content(str(target["full_path"]))
    sheets = _extract_sheet_entries(document)
    if sheets:
        response_text = f"{target['title']}의 시트 {len(sheets)}개를 정리했습니다."
    else:
        response_text = f"{target['title']}에는 별도 시트 구조가 없습니다."
    _remember_document_target(session_id, target)
    suggested_replies = [f"{target['title']} {sheet['sheet_name']} 시트 보여줘" for sheet in sheets[:3]]
    return _build_document_task_payload(
        query=query,
        task_id="sheet_list",
        skill="builtin_document_sheet_list",
        response_text=response_text,
        target=target,
        structured_payload={
            "title": target["title"],
            "format": document.get("format", ""),
            "sheets": sheets,
        },
        suggested_replies=suggested_replies or [f"{target['title']} 요약해줘"],
    )


def _resolve_document_summary_payload(query: str, session_id: str = "") -> dict[str, object] | None:
    explicit_target_query = _extract_explicit_document_target_query(query)
    if explicit_target_query and not _looks_like_document_identifier_query(explicit_target_query):
        topic_query = _primary_topic_summary_query(explicit_target_query) or explicit_target_query
        topic_candidates = _select_topic_summary_candidates(topic_query)
        if len(topic_candidates) >= 2 and not any(
            _is_exact_document_lookup_query(topic_query, candidate)
            for candidate in topic_candidates
        ):
            topic_targets = [
                _normalize_document_target(
                    {
                        "title": item["label"],
                        "path": item["path"],
                        "full_path": item["full_path"],
                        "preview": item["preview"],
                        "kind": "document",
                        "score": item["score"],
                    }
                )
                for item in topic_candidates[:3]
            ]
            topic_targets.sort(key=_topic_target_priority)
            topic_highlights: list[tuple[str, str]] = []
            for target in topic_targets:
                document = _load_document_task_content(str(target["full_path"]))
                highlight = _extract_topic_document_highlight(
                    document,
                    fallback_preview=str(target.get("preview", "")).strip(),
                )
                if not highlight:
                    continue
                topic_highlights.append((str(target["title"]), highlight))
            topic_summary_lines = _compose_topic_summary_lines(
                topic_query,
                topic_highlights,
            )
            if topic_summary_lines:
                llm_topic_payload = _generate_topic_summary_with_llm(
                    query=query,
                    topic_title=topic_query,
                    targets=topic_targets,
                    fallback_summary_lines=topic_summary_lines,
                )
                if llm_topic_payload is not None:
                    return llm_topic_payload
                return _build_topic_summary_payload(
                    query=query,
                    topic_title=topic_query,
                    targets=topic_targets,
                    summary_lines=topic_summary_lines,
                )

    target = _resolve_document_task_target(query, session_id=session_id)
    if target is None:
        return _build_document_task_clarification_payload(
            query=query,
            task_id="doc_summary",
            skill="builtin_document_summary",
            prompt="어떤 문서를 요약할지 먼저 알려주세요.",
            session_id=session_id,
            lookup_query=_strip_document_task_query(query),
        )
    document = _load_document_task_content(str(target["full_path"]))
    outline = _extract_outline_entries(document)
    summary_lines = _extract_summary_lines(document, outline)
    response_text = f"{target['title']} 요약입니다. {' '.join(summary_lines[:3])}".strip()
    _remember_document_target(session_id, target)
    return _build_document_task_payload(
        query=query,
        task_id="doc_summary",
        skill="builtin_document_summary",
        response_text=response_text,
        target=target,
        structured_payload={
            "title": target["title"],
            "format": document.get("format", ""),
            "summary_lines": summary_lines,
            "outline": outline[:8],
        },
    )


def _resolve_document_outline_payload(query: str, session_id: str = "") -> dict[str, object] | None:
    target = _resolve_document_task_target(query, session_id=session_id)
    if target is None:
        return _build_document_task_clarification_payload(
            query=query,
            task_id="doc_outline",
            skill="builtin_document_outline",
            prompt="어떤 문서의 목차를 볼지 먼저 알려주세요.",
            session_id=session_id,
            lookup_query=_strip_document_task_query(query),
        )
    document = _load_document_task_content(str(target["full_path"]))
    outline = _extract_outline_entries(document)
    if not outline:
        outline = [line for line in _extract_summary_lines(document, []) if line]
    if _is_code_document(document):
        response_text = (
            f"{target['title']}의 주요 코드 구조 {len(outline)}개를 정리했습니다."
            if outline
            else f"{target['title']}에서 눈에 띄는 코드 구조를 찾지 못했습니다."
        )
    else:
        response_text = (
            f"{target['title']}의 주요 목차 {len(outline)}개를 정리했습니다."
            if outline
            else f"{target['title']}에서 별도 목차를 찾지 못했습니다."
        )
    _remember_document_target(session_id, target)
    return _build_document_task_payload(
        query=query,
        task_id="doc_outline",
        skill="builtin_document_outline",
        response_text=response_text,
        target=target,
        structured_payload={
            "title": target["title"],
            "format": document.get("format", ""),
            "outline": outline[:12],
        },
    )


def _resolve_document_section_payload(query: str, session_id: str = "") -> dict[str, object] | None:
    requested_section = _extract_requested_document_section(query)
    relative_section = _extract_relative_document_section(query)
    if requested_section is None and relative_section is None:
        return None
    requested_kind = ""
    requested_index = 0
    target_query = query
    if requested_section is not None:
        requested_kind, requested_index = requested_section
    else:
        relative_kind, delta = relative_section
        last_section_kind = str(_session_document_state_value(session_id, "last_section_kind") or "").strip()
        remembered_kind = last_section_kind if last_section_kind in {"slide", "page"} else ""
        requested_kind = relative_kind or remembered_kind or "page"
        remembered_index = int(_session_document_state_value(session_id, "last_section_index") or 1)
        if remembered_kind and remembered_kind != requested_kind:
            remembered_index = 1
        requested_index = max(1, remembered_index + delta)
        target_query = _strip_document_task_query(query)
    target = _resolve_document_task_target(target_query, session_id=session_id)
    if target is None:
        return _build_document_task_clarification_payload(
            query=query,
            task_id="doc_section",
            skill="builtin_document_section",
            prompt="어느 문서의 슬라이드나 페이지를 볼지 먼저 알려주세요.",
            session_id=session_id,
            lookup_query=_strip_document_task_query(query),
        )
    document = _load_document_task_content(str(target["full_path"]))
    doc_format = str(document.get("format", "") or "")
    effective_kind = requested_kind
    if requested_kind == "page" and doc_format == "pptx":
        effective_kind = "slide"

    if effective_kind == "slide":
        section_lines = _extract_slide_section(document, requested_index)
        section_label = f"Slide {requested_index}"
    else:
        section_lines = _extract_page_section(document, requested_index)
        section_label = f"Page {requested_index}"

    if section_lines:
        response_text = f"{target['title']}의 {section_label} 내용을 정리했습니다."
    else:
        response_text = f"{target['title']}에서 {section_label} 내용을 찾지 못했습니다."

    _remember_document_target(session_id, target, section_kind=effective_kind, section_index=requested_index)
    suggested_replies = [
        f"다음 {'슬라이드' if effective_kind == 'slide' else '페이지'} 보여줘",
        f"이전 {'슬라이드' if effective_kind == 'slide' else '페이지'} 보여줘",
        f"{target['title']} 목차 보여줘",
    ]
    return _build_document_task_payload(
        query=query,
        task_id="doc_section",
        skill="builtin_document_section",
        response_text=response_text,
        target=target,
        structured_payload={
            "title": target["title"],
            "format": doc_format,
            "section_kind": effective_kind,
            "section_index": requested_index,
            "section_label": section_label,
            "section_lines": section_lines,
        },
        suggested_replies=suggested_replies,
    )


def _resolve_document_sheet_payload(query: str, session_id: str = "") -> dict[str, object] | None:
    selector = _extract_requested_sheet_selector(query)
    if selector is None:
        return None
    target_query = _strip_document_sheet_target_query(query)
    target = _resolve_document_task_target_from_lookup(target_query, session_id=session_id)
    if target is None:
        return _build_document_task_clarification_payload(
            query=query,
            task_id="doc_sheet",
            skill="builtin_document_sheet",
            prompt="어느 스프레드시트의 시트를 열지 먼저 알려주세요.",
            session_id=session_id,
            lookup_query=target_query,
        )
    document = _load_document_task_content(str(target["full_path"]))
    sheets = _extract_sheet_entries(document)
    selected_sheet = _select_sheet_entry(sheets, selector)
    if selected_sheet is None:
        selector_label = str(selector.get("name", "")).strip() or f"{int(selector.get('index', 0) or 0)}번째 시트"
        response_text = f"{target['title']}에서 {selector_label}를 찾지 못했습니다."
        return _build_document_task_payload(
            query=query,
            task_id="doc_sheet",
            skill="builtin_document_sheet",
            response_text=response_text,
            target=target,
            structured_payload={
                "title": target["title"],
                "format": document.get("format", ""),
                "sheet_name": "",
                "sheet_index": None,
                "column_count": 0,
                "row_count": 0,
                "header_preview": "",
                "first_row_preview": "",
                "sheets": sheets,
            },
            suggested_replies=[f"{target['title']} {sheet['sheet_name']} 시트 보여줘" for sheet in sheets[:3]],
        )
    sheet_index, sheet = selected_sheet
    response_text = f"{target['title']}의 {sheet['sheet_name']} 시트를 정리했습니다."
    _remember_document_target(
        session_id,
        target,
        sheet_name=str(sheet.get("sheet_name", "")).strip(),
        sheet_index=sheet_index,
    )
    return _build_document_task_payload(
        query=query,
        task_id="doc_sheet",
        skill="builtin_document_sheet",
        response_text=response_text,
        target=target,
        structured_payload={
            "title": target["title"],
            "format": document.get("format", ""),
            "sheet_name": sheet.get("sheet_name", ""),
            "sheet_index": sheet_index,
            "column_count": sheet.get("column_count", 0),
            "row_count": sheet.get("row_count", 0),
            "header_preview": sheet.get("header_preview", ""),
            "first_row_preview": sheet.get("first_row_preview", ""),
            "sheets": sheets,
        },
        suggested_replies=[
            f"{target['title']} sheet 목록 보여줘",
            f"{target['title']} 요약해줘",
        ],
    )


def _infer_question_prompt(text: str) -> str:
    normalized = " ".join(str(text).split()).strip()
    if not normalized:
        return ""
    if "?" in normalized:
        sentences = [part.strip() for part in normalized.split("?") if part.strip()]
        for candidate in reversed(sentences):
            if any(token in candidate for token in ("어디", "무엇", "어느", "말씀", "알려", "선택", "확인")):
                return f"{candidate}?"
        if sentences:
            return f"{sentences[0]}?"
    return ""


def _artifact_viewer_kind(type_name: str) -> str:
    normalized = type_name.strip().lower()
    if normalized in {"code_file", "code_symbol"}:
        return "code"
    if normalized in {"html", "html_document"}:
        return "html"
    if normalized == "document":
        return "document"
    if normalized == "image":
        return "image"
    if normalized == "video":
        return "video"
    if normalized == "web":
        return "web"
    return "text"


def _artifact_type_for_source(
    *,
    source_type: str,
    path: str = "",
    kind: str = "",
) -> str:
    normalized_source = source_type.strip().lower()
    normalized_kind = kind.strip().lower()
    normalized_path = path.strip().lower()
    if normalized_path.startswith(("http://", "https://")):
        return "web"
    if normalized_path.endswith((".html", ".htm")):
        return "html"
    if normalized_path.endswith((".png", ".jpg", ".jpeg", ".gif", ".webp", ".heic", ".svg")):
        return "image"
    if normalized_path.endswith((".mp4", ".mov", ".m4v", ".webm")):
        return "video"
    if normalized_source == "web":
        return "web"
    if normalized_source == "document":
        return "document"
    if normalized_kind == "code_symbol":
        return "code_symbol"
    if normalized_source == "code":
        return "code_file"
    return "text"


def _artifact_type_for_exploration_kind(kind: str) -> str:
    normalized = kind.strip().lower()
    if normalized == "document":
        return "document"
    if normalized == "filename":
        return "code_file"
    if normalized in {"class", "function"}:
        return "code_symbol"
    return "text"


def _artifact_type_for_exploration_item(*, kind: str, path: str) -> str:
    normalized_path = path.strip().lower()
    if normalized_path.startswith(("http://", "https://")):
        return "web"
    if normalized_path.endswith((".html", ".htm")):
        return "html"
    if normalized_path.endswith((".png", ".jpg", ".jpeg", ".gif", ".webp", ".heic", ".svg")):
        return "image"
    if normalized_path.endswith((".mp4", ".mov", ".m4v", ".webm")):
        return "video"
    return _artifact_type_for_exploration_kind(kind)


def _artifact_subtitle_for_exploration_kind(kind: str) -> str:
    normalized = kind.strip().lower()
    if normalized == "document":
        return "문서 후보"
    if normalized == "filename":
        return "파일 후보"
    if normalized == "class":
        return "클래스 후보"
    if normalized == "function":
        return "함수 후보"
    return "관련 항목"


def _is_absolute_path(path: str) -> bool:
    normalized = path.strip()
    return normalized.startswith("/") or normalized.startswith("http://") or normalized.startswith("https://")


def _resolve_full_path(full_path: str, short_path: str) -> str:
    """Resolve a full path, converting relative paths to absolute using knowledge_base."""
    # Already absolute — use as-is
    if _is_absolute_path(full_path):
        return full_path
    # Try to resolve relative path against knowledge_base
    candidate = full_path or short_path
    if not candidate:
        return ""
    try:
        from jarvis.app.runtime_context import resolve_knowledge_base_path
        kb = resolve_knowledge_base_path()
        resolved = (kb / candidate).resolve()
        if resolved.exists():
            return str(resolved)
    except Exception:
        pass
    return ""


def _workspace_title(interaction_mode: str, selected_type: str = "") -> str:
    normalized_type = selected_type.strip().lower()
    if normalized_type in {"image", "video"}:
        return "Media Workspace"
    if normalized_type in {"web", "html"}:
        return "Web Workspace"
    if normalized_type in {"code_file", "code_symbol"}:
        return "Code Workspace"
    if interaction_mode == "source_exploration":
        return "Source Workspace"
    if interaction_mode == "document_exploration":
        return "Document Workspace"
    return "Jarvis Workspace"


def _workspace_subtitle(
    *,
    artifact_count: int,
    citation_count: int,
    selected_label: str,
) -> str:
    parts = [f"항목 {artifact_count}개", f"근거 {citation_count}개"]
    if selected_label:
        parts.append(f"현재 선택: {selected_label}")
    return " · ".join(parts)


def _build_presentation_payload(data: dict[str, object]) -> tuple[dict[str, object] | None, list[dict[str, object]]]:
    builtin_presentation = data.get("builtin_presentation")
    builtin_artifacts = data.get("builtin_artifacts")
    if isinstance(builtin_presentation, dict) and isinstance(builtin_artifacts, list):
        return builtin_presentation, [
            artifact for artifact in builtin_artifacts if isinstance(artifact, dict)
        ]

    render_hints = data.get("render_hints") or {}
    exploration = data.get("exploration") or {}
    source_presentation = data.get("source_presentation") or {}
    citations = data.get("citations") or []
    interaction_mode = str(render_hints.get("interaction_mode", "")).strip()
    response_text = str(data.get("response", "")).strip()

    artifacts: list[dict[str, object]] = []
    artifact_index = 0
    artifact_ids_by_key: dict[tuple[str, str, str, str], str] = {}

    def add_artifact(
        *,
        type_name: str,
        title: str,
        subtitle: str = "",
        path: str = "",
        full_path: str = "",
        preview: str = "",
        source_type: str = "",
    ) -> str:
        nonlocal artifact_index
        safe_title = str(title).strip()
        safe_path = str(path).strip()
        safe_full_path = str(full_path).strip()
        safe_subtitle = str(subtitle).strip()
        key = (type_name, safe_full_path or safe_path, safe_title, safe_subtitle)
        if key in artifact_ids_by_key:
            return artifact_ids_by_key[key]
        artifact_index += 1
        artifact_id = f"artifact_{artifact_index}"
        artifacts.append({
            "id": artifact_id,
            "type": type_name,
            "title": safe_title,
            "subtitle": safe_subtitle,
            "path": safe_path,
            "full_path": _resolve_full_path(safe_full_path, safe_path),
            "preview": str(preview).strip(),
            "source_type": str(source_type).strip(),
            "viewer_kind": _artifact_viewer_kind(type_name),
        })
        artifact_ids_by_key[key] = artifact_id
        return artifact_id

    list_artifact_ids: list[str] = []
    exploration_groups = (
        ("document", exploration.get("document_candidates", [])),
        ("filename", exploration.get("file_candidates", [])),
        ("class", exploration.get("class_candidates", [])),
        ("function", exploration.get("function_candidates", [])),
    )
    for kind, raw_items in exploration_groups:
        for raw_item in raw_items:
            if not isinstance(raw_item, dict):
                continue
            title = str(raw_item.get("label", "")).strip()
            if not title:
                continue
            artifact_id = add_artifact(
                type_name=_artifact_type_for_exploration_item(
                    kind=kind,
                    path=str(raw_item.get("path", "")).strip(),
                ),
                title=title,
                subtitle=_artifact_subtitle_for_exploration_kind(kind),
                path=str(raw_item.get("path", "")).strip(),
                full_path=str(raw_item.get("path", "")).strip(),
                preview=str(raw_item.get("preview", "")).strip(),
                source_type="document" if kind == "document" else "code",
            )
            list_artifact_ids.append(artifact_id)

    source_artifact_id = ""
    if isinstance(source_presentation, dict) and source_presentation:
        preview_lines = source_presentation.get("preview_lines", [])
        preview_text = "\n".join(
            str(line).strip() for line in preview_lines if str(line).strip()
        ).strip()
        source_artifact_id = add_artifact(
            type_name=_artifact_type_for_source(
                source_type=str(source_presentation.get("source_type", "")),
                path=str(source_presentation.get("full_source_path", "")).strip()
                or str(source_presentation.get("source_path", "")).strip(),
                kind=str(source_presentation.get("kind", "")),
            ),
            title=str(source_presentation.get("title", "")).strip()
            or str(source_presentation.get("source_path", "")).strip()
            or "주요 자료",
            subtitle=str(source_presentation.get("heading_path", "")).strip()
            or "주요 근거 미리보기",
            path=str(source_presentation.get("source_path", "")).strip(),
            full_path=str(source_presentation.get("full_source_path", "")).strip(),
            preview=preview_text or str(source_presentation.get("quote", "")).strip(),
            source_type=str(source_presentation.get("source_type", "")).strip(),
        )

    # Move the source artifact (most relevant) to the front of the list
    if source_artifact_id:
        source_artifact = None
        rest = []
        for a in artifacts:
            if a.get("id") == source_artifact_id:
                source_artifact = a
            else:
                rest.append(a)
        if source_artifact:
            artifacts[:] = [source_artifact] + rest

    selected_artifact_id = source_artifact_id or (list_artifact_ids[0] if list_artifact_ids else "")
    selected_title = ""
    selected_type = ""
    if selected_artifact_id:
        for artifact in artifacts:
            if artifact.get("id") == selected_artifact_id:
                selected_title = str(artifact.get("title", "")).strip()
                selected_type = str(artifact.get("type", "")).strip()
                break

    blocks: list[dict[str, object]] = []
    if response_text:
        blocks.append({
            "id": "answer",
            "kind": "answer",
            "title": "AI 응답",
            "subtitle": "현재 요청에 대한 설명",
            "artifact_ids": [],
            "citation_labels": [],
            "empty_state": "",
        })
    if list_artifact_ids:
        blocks.append({
            "id": "list",
            "kind": "list",
            "title": "자료 목록" if interaction_mode == "document_exploration" else "소스 목록",
            "subtitle": "항목을 선택하면 상세 뷰가 바뀝니다",
            "artifact_ids": list_artifact_ids,
            "citation_labels": [],
            "empty_state": "표시할 후보가 없습니다.",
        })
    if selected_artifact_id:
        blocks.append({
            "id": "detail",
            "kind": "detail",
            "title": "상세 보기",
            "subtitle": "선택한 항목의 미리보기",
            "artifact_ids": [selected_artifact_id],
            "citation_labels": [],
            "empty_state": "왼쪽 목록에서 항목을 선택하세요.",
        })
    citation_labels = [
        str(citation.get("label", "")).strip()
        for citation in citations
        if isinstance(citation, dict) and str(citation.get("label", "")).strip()
    ]
    if citation_labels:
        blocks.append({
            "id": "evidence",
            "kind": "evidence",
            "title": "근거 자료",
            "subtitle": "응답에 사용된 출처",
            "artifact_ids": [],
            "citation_labels": citation_labels,
            "empty_state": "표시할 근거가 없습니다.",
        })

    if not blocks:
        return None, artifacts

    artifact_types = {
        str(artifact.get("type", "")).strip().lower()
        for artifact in artifacts
        if str(artifact.get("type", "")).strip()
    }
    rich_detail_types = {"document", "html", "web", "video"}
    layout = "stack"
    if list_artifact_ids and artifact_types and artifact_types.issubset({"image"}):
        layout = "gallery"
    elif (
        list_artifact_ids
        and selected_artifact_id
        and citation_labels
        and selected_type.lower() in rich_detail_types
    ):
        layout = "tabs"
    elif list_artifact_ids and selected_artifact_id:
        layout = "master_detail"
    elif (
        selected_artifact_id
        and citation_labels
        and selected_type.lower() in rich_detail_types
    ):
        layout = "split"
    elif selected_artifact_id and citation_labels:
        layout = "stack"

    presentation = {
        "layout": layout,
        "title": _workspace_title(interaction_mode, selected_type),
        "subtitle": _workspace_subtitle(
            artifact_count=len(artifacts),
            citation_count=len(citation_labels),
            selected_label=selected_title,
        ),
        "selected_artifact_id": selected_artifact_id,
        "blocks": blocks,
    }
    return presentation, artifacts


def _build_guide_payload(response: object) -> dict[str, object]:
    data = _payload_dict(response)
    directive = data.get("guide_directive") or {}
    exploration = data.get("exploration") or {}
    ui_hints = data.get("ui_hints") if isinstance(data.get("ui_hints"), dict) else {}
    answer_kind = str(data.get("answer_kind", "retrieval_result") or "retrieval_result")
    inferred_prompt = _infer_question_prompt(str(data.get("response", "")))
    clarification_prompt = directive.get("clarification_prompt", "") or inferred_prompt
    missing_slots = directive.get("missing_slots", [])
    clarification_options = directive.get("suggested_replies", [])
    if not clarification_options:
        clarification_options = (
            [item.get("label", "") for item in exploration.get("document_candidates", [])[:2]]
            + [item.get("label", "") for item in exploration.get("file_candidates", [])[:2]]
            + [item.get("label", "") for item in exploration.get("class_candidates", [])[:2]]
            + [item.get("label", "") for item in exploration.get("function_candidates", [])[:2]]
        )
    has_clarification = bool(clarification_prompt or missing_slots)
    presentation, artifacts = _build_presentation_payload(data)
    show_documents_default = answer_kind == "retrieval_result"
    show_repository_default = answer_kind == "retrieval_result"
    show_inspector_default = bool(data.get("citations"))
    if answer_kind in {"utility_result", "action_result"}:
        presentation = None
        artifacts = []
    return {
        "loop_stage": directive.get(
            "loop_stage",
            "waiting_user_reply" if has_clarification else "presenting",
        ),
        "clarification_prompt": clarification_prompt,
        "suggested_replies": directive.get("suggested_replies", []),
        "clarification_options": [
            label for label in clarification_options if str(label).strip()
        ],
        "missing_slots": missing_slots,
        "clarification_reasons": [
            str(slot).replace("_", " ") for slot in missing_slots
        ],
        "intent": directive.get("intent", ""),
        "skill": directive.get("skill", ""),
        "should_hold": bool(directive.get("should_hold", False)),
        "has_clarification": has_clarification,
        "interaction_mode": data.get("render_hints", {}).get("interaction_mode", ""),
        "exploration_mode": exploration.get("mode", ""),
        "target_file": exploration.get("target_file", ""),
        "target_document": exploration.get("target_document", ""),
        "presentation": presentation,
        "artifacts": artifacts,
        "ui_hints": {
            "show_documents": bool(ui_hints.get("show_documents", show_documents_default)),
            "show_repository": bool(ui_hints.get("show_repository", show_repository_default)),
            "show_inspector": bool(ui_hints.get("show_inspector", show_inspector_default)),
            "preferred_view": str(ui_hints.get("preferred_view", "dashboard" if answer_kind in {"utility_result", "action_result"} else "")),
        },
    }


def _start_background_tts_warmup() -> dict[str, bool]:
    global _tts_warmup_running, _tts_warmup_ready
    with _tts_warmup_lock:
        if _tts_warmup_ready:
            return {"started": False, "running": False, "warmed": True}
        if _tts_warmup_running:
            return {"started": False, "running": True, "warmed": False}
        _tts_warmup_running = True

    def _run() -> None:
        global _tts_warmup_running, _tts_warmup_ready
        try:
            warmed = _warmup_tts()
        except Exception:
            warmed = False
        with _tts_warmup_lock:
            _tts_warmup_running = False
            _tts_warmup_ready = warmed or _tts_warmup_ready

    threading.Thread(
        target=_run,
        daemon=True,
        name="jarvis-tts-warmup",
    ).start()
    return {"started": True, "running": True, "warmed": False}


def _mark_tts_ready() -> None:
    global _tts_warmup_ready, _tts_warmup_running
    with _tts_warmup_lock:
        _tts_warmup_ready = True
        _tts_warmup_running = False


def _prefetch_tts_cache(text: str) -> None:
    cleaned = text.strip()
    if not cleaned:
        return
    try:
        _synthesize_speech(text=cleaned)
    except Exception:
        pass


def _tts_prefetch_segments(text: str) -> tuple[str, ...]:
    cleaned = text.strip()
    if not cleaned:
        return ()
    parts = [
        part.strip()
        for part in cleaned.split(" / ")
        if part.strip()
    ]
    if len(parts) > 1:
        return tuple(parts)
    return (cleaned,)


def _prefetch_tts_segments(text: str) -> None:
    for segment in _tts_prefetch_segments(text):
        _prefetch_tts_cache(segment)


def _prime_tts_cache_async(response_payload: object) -> None:
    if not isinstance(response_payload, dict):
        return
    spoken_text = str(response_payload.get("spoken_response", "")).strip()
    if not spoken_text:
        return
    thread = threading.Thread(
        target=_prefetch_tts_segments,
        args=(spoken_text,),
        daemon=True,
        name="jarvis-tts-prefetch",
    )
    thread.start()


def _prefetch_query_tts_async(query: str) -> dict[str, object]:
    if _tts_backend() not in {"qwen3", "auto"}:
        return {"started": False, "predicted_text": ""}
    predicted_text = predict_prefetchable_spoken_response(query)
    if not predicted_text:
        return {"started": False, "predicted_text": ""}
    thread = threading.Thread(
        target=_prefetch_tts_segments,
        args=(predicted_text,),
        daemon=True,
        name="jarvis-query-tts-prefetch",
    )
    thread.start()
    return {"started": True, "predicted_text": predicted_text}


def _inject_document_context(query: str, document_path: str) -> str:
    """Read the specified document and prepend its content as context to the query.

    This allows the LLM to answer questions about a specific open document
    instead of relying on RAG keyword search which may return unrelated results.
    """
    from pathlib import Path

    path = Path(document_path).expanduser()
    if not path.is_absolute() or not path.is_file():
        from jarvis.app.runtime_context import resolve_knowledge_base_path
        resolved = (resolve_knowledge_base_path() / document_path).resolve()
        if resolved.is_file():
            path = resolved
    if not path.is_file():
        return query

    # For text-readable files, read content directly
    TEXT_EXTENSIONS = {
        ".py", ".ts", ".tsx", ".js", ".jsx", ".swift", ".kt", ".java", ".c", ".cpp",
        ".h", ".hpp", ".cs", ".rb", ".rs", ".go", ".php", ".sh", ".zsh", ".bash",
        ".r", ".m", ".mm", ".sql", ".md", ".txt", ".json", ".yaml", ".yml", ".xml",
        ".html", ".css", ".scss", ".toml", ".ini", ".cfg", ".conf", ".env", ".log",
        ".vue", ".svelte", ".dart", ".lua",
    }
    ext = path.suffix.lower()
    if ext not in TEXT_EXTENSIONS:
        # For binary documents (PDF, DOCX, etc.), try to read from indexed chunks
        try:
            from jarvis.app.bootstrap import init_database
            from jarvis.app.config import JarvisConfig

            config = JarvisConfig(data_dir=os.getenv("JARVIS_DATA_DIR", ""))
            db = init_database(config)
            rows = db.execute(
                "SELECT c.text FROM chunks c JOIN documents d ON c.document_id = d.id "
                "WHERE d.path = ? ORDER BY c.chunk_index LIMIT 30",
                (str(path),),
            ).fetchall()
            if rows:
                content = "\n\n".join(row[0] for row in rows)
                return (
                    f"[문서 컨텍스트: {path.name}]\n{content[:20000]}\n"
                    f"[/문서 컨텍스트]\n\n{query}"
                )
        except Exception:
            pass
        return query

    try:
        content = path.read_text(encoding="utf-8", errors="replace")[:20000]
    except Exception:
        return query

    return f"[문서 컨텍스트: {path.name}]\n{content}\n[/문서 컨텍스트]\n\n{query}"


def _get_doc_analysis_backend():
    """Get the LLM backend from the already-loaded runtime context.

    Reuses the same model that _run_menu_bridge_ask_with_fallback uses,
    avoiding duplicate model loading.
    """
    import logging as _logging
    _log = _logging.getLogger(__name__)

    model_chain = _menu_bar_model_chain()
    for model_id in model_chain:
        if model_id.strip().lower() == "stub":
            continue
        try:
            context = _get_runtime_context(model_id=model_id)
            # Access the backend through orchestrator → llm_generator → _backend
            generator = getattr(context.orchestrator, '_llm_generator', None)
            if generator is None:
                continue
            backend = getattr(generator, '_backend', None)
            if backend is not None and getattr(backend, 'is_loaded', False):
                _log.info("Document analysis: reusing backend %s", getattr(backend, 'model_id', model_id))
                return backend
        except Exception as exc:
            _log.warning("Failed to get runtime context for %s: %s", model_id, exc)
            continue

    _log.error("No loaded LLM backend found in runtime contexts")
    return None


_MAX_CONTINUATION_ROUNDS = 3


def _generate_full_response(backend: object, prompt: str, context: str) -> str:
    """Generate a complete LLM response with automatic continuation.

    If the model hits max_tokens before EOS (response was truncated),
    feeds the partial response back as context and asks the model to
    continue. Repeats up to _MAX_CONTINUATION_ROUNDS times, then
    concatenates all parts into the full response.
    """
    import logging as _logging
    _log = _logging.getLogger(__name__)

    parts: list[str] = []

    for round_idx in range(_MAX_CONTINUATION_ROUNDS + 1):
        if round_idx == 0:
            current_prompt = prompt
            current_context = context
        else:
            # Continuation: feed partial response back, ask to continue
            accumulated = "".join(parts)
            current_context = context
            current_prompt = (
                f"{prompt}\n\n"
                f"[이전 응답 (이어서 작성할 것)]\n{accumulated}\n[/이전 응답]\n\n"
                "위 응답이 중간에 잘렸습니다. 잘린 부분부터 이어서 작성하세요. "
                "이전 내용을 반복하지 말고, 바로 이어서 계속하세요."
            )

        chunk, hit_limit = _generate_single_chunk(backend, current_prompt, current_context)

        if chunk:
            parts.append(chunk)

        if not hit_limit:
            # Model finished naturally (EOS) — done
            break

        _log.info("Document analysis: continuation round %d (accumulated %d chars)", round_idx + 1, sum(len(p) for p in parts))

    return "".join(parts)


_DOCUMENT_ANALYSIS_SYSTEM_PROMPT = (
    "당신은 소스 코드 및 문서 분석 전문가입니다.\n\n"
    "답변 규칙:\n"
    "- 주어진 소스 코드 또는 문서를 상세하게 분석하세요.\n"
    "- 간결하게 요약하지 마세요. 충분히 길고 상세하게 설명하세요.\n"
    "- 클래스, 구조체, 함수, 메서드의 역할과 동작을 각각 설명하세요.\n"
    "- 데이터 흐름, 설계 패턴, 외부 의존성을 포함하세요.\n"
    "- 한국어로 답변하세요."
)


def _generate_single_chunk(backend: object, prompt: str, context: str) -> tuple[str, bool]:
    """Generate one chunk via the backend. Returns (text, hit_max_tokens).

    hit_max_tokens=True means the response was truncated (no EOS), needs continuation.
    """
    # Use document analysis system prompt (NOT the default RAG prompt
    # which instructs "1-3문장으로 간결하게" and causes early EOS)
    system_message = _DOCUMENT_ANALYSIS_SYSTEM_PROMPT
    if context.strip():
        system_message += f"\n\n===== 참고 자료 =====\n{context}\n===== 참고 자료 끝 ====="

    tokenizer = getattr(backend, '_tokenizer', None)
    model = getattr(backend, '_model', None)

    # MLXBackend path
    if tokenizer is not None and model is not None:
        from mlx_lm import generate as mlx_generate
        from mlx_lm.sample_utils import make_sampler

        messages = [
            {"role": "system", "content": system_message},
            {"role": "user", "content": prompt},
        ]
        template_kwargs: dict = {}
        try:
            tokenizer.apply_chat_template(messages, add_generation_prompt=True, enable_thinking=False)
            template_kwargs["enable_thinking"] = False
        except (TypeError, Exception):
            pass
        formatted = tokenizer.apply_chat_template(messages, add_generation_prompt=True, **template_kwargs)
        prompt_tokens = len(formatted) if isinstance(formatted, list) else len(tokenizer.encode(formatted))
        context_window = getattr(backend, '_context_window', 32768)
        max_tokens = context_window - prompt_tokens
        if max_tokens < 256:
            return "", False

        sampler = make_sampler(0.7, 0.9, 0.0, 1)
        response = mlx_generate(model, tokenizer, prompt=formatted, max_tokens=max_tokens, sampler=sampler)

        # Detect truncation: count response tokens vs max_tokens
        response_tokens = len(tokenizer.encode(response)) if response else 0
        hit_limit = response_tokens >= max_tokens - 10  # within 10 tokens of limit

        return response, hit_limit

    # GemmaVlmBackend path
    processor = getattr(backend, '_processor', None)
    config = getattr(backend, '_config', None)
    if processor is not None and model is not None:
        from mlx_vlm import generate as vlm_generate
        from mlx_vlm.prompt_utils import apply_chat_template as vlm_apply_chat_template
        full_prompt = f"{system_message}\n\n{prompt}"
        formatted = vlm_apply_chat_template(processor, config, full_prompt, num_images=0)
        context_window = getattr(backend, '_context_window', 131072)
        try:
            prompt_tokens = len(processor.tokenizer.encode(formatted))
        except Exception:
            prompt_tokens = len(formatted) // 4
        max_tokens = context_window - prompt_tokens
        if max_tokens < 256:
            return "", False

        output = vlm_generate(model, processor, formatted, config=config, max_tokens=max_tokens, temperature=0.7, verbose=False)
        response = output.text if hasattr(output, "text") else str(output)

        try:
            response_tokens = len(processor.tokenizer.encode(response))
        except Exception:
            response_tokens = len(response) // 4
        hit_limit = response_tokens >= max_tokens - 10
        return response, hit_limit

    # Fallback
    response = backend.generate(prompt, context, "document_explanation")
    return response, False


def _ask_about_document(query: str, document_path: str) -> tuple[dict[str, object] | None, str]:
    """Answer questions about a specific document using a dedicated LLM backend.

    Bypasses the RAG pipeline entirely — reads the file directly and sends
    to Gemma 4 E4B (or EXAONE fallback) with a code-analysis prompt.

    Returns (response_payload, "") on success or (None, reason) on failure.
    """
    import logging as _logging
    from pathlib import Path

    _log = _logging.getLogger(__name__)

    path = Path(document_path).expanduser()
    if not path.is_absolute() or not path.is_file():
        # Try resolving as KB-relative path
        from jarvis.app.runtime_context import resolve_knowledge_base_path
        kb_root = resolve_knowledge_base_path()
        resolved = (kb_root / document_path).resolve()
        if resolved.is_file():
            path = resolved
        elif not path.is_file():
            return None, f"파일이 존재하지 않습니다: {document_path} (KB root: {kb_root})"

    filename = path.name

    # Read file content
    TEXT_EXTENSIONS = {
        ".py", ".ts", ".tsx", ".js", ".jsx", ".swift", ".kt", ".java", ".c", ".cpp",
        ".h", ".hpp", ".cs", ".rb", ".rs", ".go", ".php", ".sh", ".zsh", ".bash",
        ".r", ".m", ".mm", ".sql", ".md", ".txt", ".json", ".yaml", ".yml", ".xml",
        ".html", ".css", ".scss", ".toml", ".ini", ".cfg", ".conf", ".vue", ".svelte",
    }
    ext = path.suffix.lower()
    file_content = ""
    if ext in TEXT_EXTENSIONS:
        try:
            file_content = path.read_text(encoding="utf-8", errors="replace")[:20000]
        except Exception as exc:
            return None, f"파일 읽기 실패: {exc}"
    if not file_content:
        context_text = _inject_document_context("", document_path).strip()
        if context_text:
            import re
            m = re.search(r"\[문서 컨텍스트:.*?\]\n(.*?)\n\[/문서 컨텍스트\]", context_text, re.DOTALL)
            file_content = m.group(1) if m else context_text
    if not file_content:
        return None, f"파일 내용을 읽을 수 없습니다 (ext={ext}, path={document_path})"

    backend = _get_doc_analysis_backend()
    if backend is None:
        return None, "LLM 백엔드 로드 실패 (Gemma, EXAONE 모두 사용 불가)"

    backend_name = getattr(backend, '_model_id', 'unknown')

    # Dynamically fit file content within context window.
    # Code (ASCII) ≈ 3 chars/token, Korean response ≈ 1.5 chars/token.
    # Allocate 1/3 of context window for file, 2/3 for response.
    ctx_window = getattr(backend, '_context_window', 8192)
    prompt_overhead_tokens = 400  # system prompt + analysis prompt
    usable_tokens = ctx_window - prompt_overhead_tokens
    file_token_budget = usable_tokens // 3
    file_char_budget = file_token_budget * 3  # code is ~3 chars/token

    if len(file_content) > file_char_budget:
        file_content = file_content[:file_char_budget] + f"\n\n... (전체 파일 중 {file_char_budget}자만 포함)"

    evidence_context = f"[파일: {filename}]\n{file_content}"
    analysis_prompt = (
        f"{query}\n\n"
        f"위 '{filename}' 파일을 상세히 분석하여 한국어로 설명하세요."
    )

    try:
        answer = _generate_full_response(backend, analysis_prompt, evidence_context)
    except Exception as exc:
        _log.error("Document analysis failed: %s", exc)
        return None, f"LLM 생성 실패 (backend={backend_name}): {exc}"

    if not answer or not answer.strip():
        return None, f"LLM이 빈 응답을 반환했습니다 (backend={backend_name})"

    from jarvis.service.builtin_capabilities import _response_payload, _presentation, _block, _artifact

    doc_artifact = _artifact(
        artifact_id="doc_context_0",
        type_name="code" if Path(document_path).suffix.lower() in {
            ".py", ".ts", ".tsx", ".js", ".jsx", ".swift", ".kt", ".java",
            ".c", ".cpp", ".h", ".cs", ".rb", ".rs", ".go", ".sh",
        } else "document",
        title=filename,
        subtitle="문서 컨텍스트 질문",
        path=document_path,
        full_path=document_path,
        preview=document_path,
        source_type="document",
    )

    payload = _response_payload(
        query=query,
        response_text=answer.strip(),
        spoken_text=answer.strip(),
        intent="document_explanation",
        skill="direct_document_qa",
        source_profile="knowledge_base",
        primary_source_type="document",
        artifacts=[doc_artifact],
        citations=[{
            "label": filename,
            "source_path": filename,
            "full_source_path": document_path,
            "source_type": "document",
            "quote": "",
            "relevance_score": 1.0,
        }],
        presentation=_presentation(
            layout="stack",
            title="Document Analysis",
            subtitle=filename,
            selected_artifact_id="doc_context_0",
            blocks=[
                _block(block_id="answer", kind="answer", title="분석 결과", subtitle="소스 코드 분석"),
                _block(
                    block_id="detail",
                    kind="detail",
                    title="문서",
                    subtitle="원본 소스",
                    artifact_ids=["doc_context_0"],
                ),
            ],
        ),
    )
    return payload, ""


class JarvisApplicationService:
    """Backend service facade for frontend clients.

    This class intentionally owns business flow mapping while staying agnostic
    to the transport (stdio, socket, http, websocket).
    """

    def handle(self, request: RpcRequest) -> RpcResponse:
        try:
            if request.request_type == "runtime_state":
                health = _health_light()
                return ok_response(
                    request=request,
                    payload={
                        "health": health,
                        "service": {
                            "contract_version": "2026-03-26",
                            "frontend_mode": "multi-client",
                            "runtime_owner": "backend-service",
                        },
                    },
                )

            if request.request_type == "health":
                return ok_response(request=request, payload={"health": _health_light()})

            if request.request_type == "normalize_query":
                text = str(request.payload.get("text", "")).strip()
                normalized = _normalize_query(query=text)
                return ok_response(
                    request=request,
                    payload={"normalized_query": normalized.normalized_query},
                )

            if request.request_type == "repair_transcript":
                text = str(request.payload.get("text", ""))
                repaired = build_transcript_repair(text)
                return ok_response(
                    request=request,
                    payload={
                        "transcript_repair": {
                            "raw_text": repaired.raw_text,
                            "repaired_text": repaired.repaired_text,
                            "display_text": repaired.display_text,
                            "final_query": repaired.final_query,
                        }
                    },
                )

            if request.request_type == "navigation_window":
                text = str(request.payload.get("text", "")).strip()
                state = _build_navigation_window(query=text, model_id="menu-bar-rpc")
                return ok_response(request=request, payload={"navigation": asdict(state)})

            if request.request_type == "transcribe_file":
                audio_path = str(request.payload.get("audio_path", "")).strip()
                if not audio_path:
                    return error_response(
                        request=request,
                        code="INVALID_ARGUMENT",
                        message="audio_path is required",
                    )
                transcript = _transcribe_file(audio_path=audio_path)
                return ok_response(
                    request=request,
                    payload={
                        "transcript": transcript.transcript,
                        "audio_path": str(Path(audio_path).expanduser()),
                    },
                )

            if request.request_type == "synthesize_speech":
                text = str(request.payload.get("text", "")).strip()
                if not text:
                    return error_response(
                        request=request,
                        code="INVALID_ARGUMENT",
                        message="text is required",
                    )
                speech = _synthesize_speech(text=text)
                _mark_tts_ready()
                return ok_response(
                    request=request,
                    payload={"speech": asdict(speech)},
                )

            if request.request_type == "warmup_tts":
                return ok_response(
                    request=request,
                    payload={"tts": _start_background_tts_warmup()},
                )

            if request.request_type == "prefetch_query_tts":
                text = str(request.payload.get("text", "")).strip()
                if not text:
                    return error_response(
                        request=request,
                        code="INVALID_ARGUMENT",
                        message="text is required",
                    )
                return ok_response(
                    request=request,
                    payload={"tts_prefetch": _prefetch_query_tts_async(text)},
                )

            if request.request_type == "export_draft":
                content = str(request.payload.get("content", ""))
                destination = str(request.payload.get("destination", "")).strip()
                approved = bool(request.payload.get("approved", False))
                if not destination:
                    return error_response(
                        request=request,
                        code="INVALID_ARGUMENT",
                        message="destination is required",
                    )
                export = _export_draft(
                    content=content,
                    destination=Path(destination).expanduser(),
                    approved=approved,
                )
                return ok_response(
                    request=request,
                    payload={"export": asdict(export)},
                )

            if request.request_type == "ask_text":
                text = str(request.payload.get("text", "")).strip()
                if not text:
                    return error_response(
                        request=request,
                        code="INVALID_ARGUMENT",
                        message="text is required",
                    )
                context_document_path = str(request.payload.get("context_document_path", "")).strip()
                if context_document_path:
                    # Direct LLM call — bypass RAG entirely
                    doc_result, doc_fail_reason = _ask_about_document(text, context_document_path)
                    if doc_result is not None:
                        _prime_tts_cache_async(doc_result)
                        return ok_response(
                            request=request,
                            payload={
                                "response": doc_result,
                                "answer": _build_answer_payload(doc_result),
                                "guide": _build_guide_payload(doc_result),
                            },
                        )
                    # Return diagnostic with specific failure reason (do NOT fall to RAG)
                    from jarvis.service.builtin_capabilities import _response_payload as _rp
                    fail_msg = f"문서 분석 실패: {doc_fail_reason}"
                    diag = _rp(
                        query=text,
                        response_text=fail_msg,
                        spoken_text=fail_msg,
                        intent="document_explanation",
                        skill="direct_document_qa",
                        source_profile="knowledge_base",
                        primary_source_type="document",
                        artifacts=[],
                        presentation=None,
                    )
                    return ok_response(
                        request=request,
                        payload={
                            "response": diag,
                            "answer": _build_answer_payload(diag),
                            "guide": _build_guide_payload(diag),
                        },
                    )
                else:
                    response_payload = resolve_builtin_capability(
                        text,
                    runtime_status_resolver=_health_light,
                    calendar_view_resolver=lambda query: _resolve_calendar_view_payload(query, request.session_id),
                    calendar_update_resolver=lambda query: _resolve_calendar_update_payload(query, request.session_id),
                    calendar_create_resolver=lambda query: _resolve_calendar_create_payload(query, request.session_id),
                    calendar_followup_resolver=lambda query: _resolve_relative_calendar_followup_payload(query, request.session_id),
                    document_open_resolver=lambda query: _resolve_document_open_payload(query, request.session_id),
                    recent_context_resolver=lambda query: _resolve_recent_context_payload(query, request.session_id),
                    document_summary_resolver=lambda query: _resolve_document_summary_payload(query, request.session_id),
                    document_outline_resolver=lambda query: _resolve_document_outline_payload(query, request.session_id),
                    document_sheet_list_resolver=lambda query: _resolve_document_sheet_list_payload(query, request.session_id),
                    document_sheet_resolver=lambda query: _resolve_document_sheet_payload(query, request.session_id),
                    document_section_resolver=lambda query: _resolve_document_section_payload(query, request.session_id),
                )
                if response_payload is None:
                    response_payload = _build_action_map_execution_response(text)
                if response_payload is None:
                    envelope = _run_menu_bridge_ask_with_fallback(query=text, session_id=request.session_id)
                    response_payload = envelope.get("query_result")
                    if not isinstance(response_payload, dict):
                        return error_response(
                            request=request,
                            code="INVALID_RESPONSE",
                            message="menu_bridge ask returned no query_result",
                        )
                    _record_unmapped_skill_request(
                        query=text,
                        session_id=request.session_id,
                        response_payload=response_payload,
                    )
                if (
                    isinstance(response_payload, dict)
                    and str(response_payload.get("task_id", "")).strip() == "relative_date"
                ):
                    structured_payload = response_payload.get("structured_payload")
                    if isinstance(structured_payload, dict):
                        _remember_relative_date_payload(request.session_id, structured_payload)
                if (
                    isinstance(response_payload, dict)
                    and str(response_payload.get("task_id", "")).strip() in {"calendar_create", "calendar_update"}
                ):
                    structured_payload = response_payload.get("structured_payload")
                    if isinstance(structured_payload, dict):
                        _remember_calendar_action_payload(
                            request.session_id,
                            structured_payload,
                            task_id=str(response_payload.get("task_id", "")).strip() or "calendar_create",
                        )
                _prime_tts_cache_async(response_payload)
                return ok_response(
                    request=request,
                    payload={
                        "response": response_payload,
                        "answer": _build_answer_payload(response_payload),
                        "guide": _build_guide_payload(response_payload),
                    },
                )

            return error_response(
                request=request,
                code="UNKNOWN_REQUEST_TYPE",
                message=f"unsupported request_type: {request.request_type}",
            )
        except FileNotFoundError as exc:
            return error_response(
                request=request,
                code="NOT_FOUND",
                message=str(exc),
            )
        except Exception as exc:
            return error_response(
                request=request,
                code="INTERNAL_ERROR",
                message=str(exc),
                retryable=False,
            )
