"""Application service entrypoints shared by all frontends."""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
import json
import os
import shlex
import subprocess
import sys

from jarvis.cli.menu_bridge import (
    _build_navigation_window,
    _export_draft,
    _health_light,
    _normalize_query,
    _run_query,
    _synthesize_speech,
    _transcribe_file,
)
from jarvis.service.protocol import RpcRequest, RpcResponse, error_response, ok_response

_DEFAULT_MENU_BAR_MODEL_CHAIN = ("qwen3.5:9b", "stub")
_DEFAULT_MENU_BRIDGE_ASK_TIMEOUT_SECONDS = 50
_DEFAULT_MENU_BRIDGE_STUB_TIMEOUT_SECONDS = 18


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


def _run_menu_bridge_ask_with_fallback(*, query: str) -> dict[str, object]:
    last_error: Exception | None = None
    for model_id in _menu_bar_model_chain():
        try:
            return _run_menu_bridge_subprocess(
                command="ask",
                args=["--query", query, "--model", model_id],
            )
        except Exception as exc:
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
                return ok_response(
                    request=request,
                    payload={"speech": asdict(speech)},
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
