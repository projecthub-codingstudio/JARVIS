"""Application service entrypoints shared by all frontends."""

from __future__ import annotations

import atexit
from dataclasses import asdict
from pathlib import Path
import json
import os
import shlex
import subprocess
import sys
import threading

from jarvis.cli.menu_bridge import (
    _build_context,
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
from jarvis.app.runtime_context import shutdown_runtime_context
from jarvis.service.protocol import RpcRequest, RpcResponse, error_response, ok_response
from jarvis.spoken_response_prefetch import predict_prefetchable_spoken_response
from jarvis.transcript_repair import build_transcript_repair

_DEFAULT_MENU_BAR_MODEL_CHAIN = ("stub",)
_DEFAULT_MENU_BRIDGE_ASK_TIMEOUT_SECONDS = 50
_DEFAULT_MENU_BRIDGE_STUB_TIMEOUT_SECONDS = 18
_tts_warmup_lock = threading.Lock()
_tts_warmup_running = False
_tts_warmup_ready = False
_runtime_context_lock = threading.Lock()
_runtime_contexts: dict[str, object] = {}
_ask_execution_lock = threading.Lock()


def _menu_bar_model_chain() -> tuple[str, ...]:
    raw = os.getenv("JARVIS_MENU_BAR_MODEL_CHAIN", "").strip()
    if not raw:
        return _DEFAULT_MENU_BAR_MODEL_CHAIN
    models = tuple(part.strip() for part in raw.split(",") if part.strip())
    return models or _DEFAULT_MENU_BAR_MODEL_CHAIN


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
    with _runtime_context_lock:
        contexts = list(_runtime_contexts.values())
        _runtime_contexts.clear()
    _shutdown_runtime_contexts(contexts)


def _run_menu_bridge_query_in_process(*, query: str, model_id: str) -> dict[str, object]:
    context = _get_runtime_context(model_id=model_id)
    response = _run_query_in_context(
        query=query,
        model_id=model_id,
        context=context,
    )
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


def _run_menu_bridge_ask_with_fallback(*, query: str) -> dict[str, object]:
    last_error: Exception | None = None
    model_chain = _menu_bar_model_chain()
    for index, model_id in enumerate(model_chain):
        try:
            with _ask_execution_lock:
                envelope = _run_menu_bridge_query_in_process(
                    query=query,
                    model_id=model_id,
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
    return {
        "text": natural_text,
        "spoken_text": natural_text,
        "has_evidence": bool(data.get("has_evidence", False)),
        "citation_count": len(data.get("citations", [])),
        "full_response_path": data.get("full_response_path"),
    }


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


def _build_guide_payload(response: object) -> dict[str, object]:
    data = _payload_dict(response)
    directive = data.get("guide_directive") or {}
    exploration = data.get("exploration") or {}
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
                envelope = _run_menu_bridge_ask_with_fallback(query=text)
                response_payload = envelope.get("query_result")
                if not isinstance(response_payload, dict):
                    return error_response(
                        request=request,
                        code="INVALID_RESPONSE",
                        message="menu_bridge ask returned no query_result",
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
