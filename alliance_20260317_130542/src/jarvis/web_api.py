"""FastAPI bridge for web UI integration."""

from __future__ import annotations

import asyncio
import mimetypes
import os
import sys
import uuid
import argparse
from pathlib import Path
from typing import Any

from fastapi import FastAPI, WebSocket, HTTPException, WebSocketDisconnect, UploadFile, File, Form, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request as StarletteRequest
from starlette.responses import Response as StarletteResponse
from pydantic import BaseModel, Field

import logging
import threading
import time as _time

from jarvis.service.protocol import RpcRequest, RpcResponse

logger = logging.getLogger(__name__)

app = FastAPI(
    title="JARVIS Web API",
    description="HTTP/WebSocket bridge for JARVIS backend",
    version="0.1.0",
)

# CORS configuration for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://0.0.0.0:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: StarletteRequest, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response


app.add_middleware(SecurityHeadersMiddleware)

_ALLOWED_ORIGINS = {
    "http://localhost:3000", "http://127.0.0.1:3000",
    "http://localhost:5173", "http://127.0.0.1:5173",
}


def _check_origin(request: Request) -> None:
    """Reject cross-origin requests from unknown origins on destructive endpoints."""
    origin = request.headers.get("origin")
    if origin and origin not in _ALLOWED_ORIGINS:
        raise HTTPException(status_code=403, detail="Cross-origin request denied")


# Lazy-loaded service — heavy imports (MLX, Whisper, TTS) happen in background
_service_instance = None
_service_lock = threading.Lock()
_service_ready = threading.Event()


def _init_service_background() -> None:
    """Load JarvisApplicationService in a background thread."""
    global _service_instance
    try:
        from jarvis.service.application import JarvisApplicationService
        _service_instance = JarvisApplicationService()
        _service_ready.set()
        logger.info("JarvisApplicationService initialized")
    except Exception as exc:
        logger.error("Failed to initialize service: %s", exc)
        _service_ready.set()  # unblock waiters even on failure


def _get_service():
    """Get the service instance, returning None if not yet ready."""
    return _service_instance


# Start background init on module load — server starts immediately
threading.Thread(target=_init_service_background, daemon=True, name="service-init").start()


# ── Indexing state tracker ──────────────────────────────────
_index_lock = threading.Lock()
_index_state: dict[str, object] = {
    "status": "idle",       # idle | scanning | indexing | done | error
    "processed": 0,
    "total": 0,
    "last_completed": None,  # ISO timestamp
    "error": None,
}


def _get_index_state() -> dict[str, object]:
    """Return a snapshot of the current indexing state."""
    with _index_lock:
        return dict(_index_state)


def _trigger_reindex(*, auto: bool = False) -> bool:
    """Start background indexing if not already running. Returns True if started."""
    if not _index_lock.acquire(blocking=False):
        return False

    # Check if already running (lock acquired but status is active)
    if _index_state["status"] in ("scanning", "indexing"):
        _index_lock.release()
        return False

    def _run() -> None:
        from jarvis.app.bootstrap import init_database
        from jarvis.app.config import JarvisConfig
        from jarvis.app.runtime_context import resolve_knowledge_base_path, is_indexable, run_indexing
        from jarvis.cli.menu_bridge import resolve_menubar_data_dir

        db = None
        try:
            _index_state["status"] = "scanning"
            _index_state["processed"] = 0
            _index_state["total"] = 0
            _index_state["error"] = None

            kb_path = resolve_knowledge_base_path()
            data_dir = resolve_menubar_data_dir()
            config = JarvisConfig(
                data_dir=data_dir,
                watched_folders=[kb_path] if kb_path.exists() else [],
            )
            db = init_database(config)

            # Count indexable files
            files = [f for f in kb_path.rglob("*") if f.is_file() and is_indexable(f)]
            _index_state["total"] = len(files)
            _index_state["status"] = "indexing"

            # Use a reporter to track progress
            progress = {"count": 0}

            def _reporter(msg: str) -> None:
                if "Indexing " in msg and "/" in msg:
                    progress["count"] += 1
                    _index_state["processed"] = progress["count"]

            run_indexing(
                db,
                kb_path,
                data_dir=data_dir,
                start_background_backfill=True,
                reporter=_reporter,
            )

            _index_state["status"] = "done"
            _index_state["last_completed"] = _time.strftime("%Y-%m-%dT%H:%M:%S")
            logger.info("Reindex complete: %d files processed (%s)", _index_state["total"], "auto" if auto else "manual")
        except Exception as exc:
            _index_state["status"] = "error"
            _index_state["error"] = str(exc)
            logger.error("Reindex failed: %s", exc)
        finally:
            if db is not None:
                db.close()
            _index_lock.release()

    threading.Thread(target=_run, daemon=True, name="reindex-worker").start()
    return True


_auto_detect_last_check = 0.0  # throttle to once per 60s


def _auto_detect_new_files(health_data: dict) -> None:
    """Compare KB file count vs indexed doc count; auto-trigger reindex if mismatch.
    Runs file scan in a background thread to avoid blocking health endpoint."""
    global _auto_detect_last_check

    if _index_state["status"] in ("scanning", "indexing"):
        return

    now = _time.time()
    if now - _auto_detect_last_check < 60:
        return
    _auto_detect_last_check = now

    doc_count = health_data.get("doc_count", 0)
    failed_count = health_data.get("failed_doc_count", 0)
    indexed_count = doc_count + failed_count

    def _check_and_trigger() -> None:
        try:
            from jarvis.app.runtime_context import resolve_knowledge_base_path, is_indexable

            kb_path = resolve_knowledge_base_path()
            if not kb_path.exists():
                return

            file_count = sum(1 for f in kb_path.rglob("*") if f.is_file() and is_indexable(f))

            if file_count > indexed_count:
                logger.info("Auto-reindex: %d files on disk vs %d indexed", file_count, indexed_count)
                _trigger_reindex(auto=True)
        except Exception:
            pass

    threading.Thread(target=_check_and_trigger, daemon=True, name="auto-detect").start()


# Request/Response models
class AskRequest(BaseModel):
    text: str = Field(max_length=16000)
    session_id: str = Field(max_length=128)
    context_document_paths: list[str] | None = None


class AskResponse(BaseModel):
    response: dict[str, Any]
    answer: dict[str, Any]
    guide: dict[str, Any]


class HealthResponse(BaseModel):
    health: dict[str, Any]


class NormalizeRequest(BaseModel):
    text: str = Field(max_length=16000)


class NormalizeResponse(BaseModel):
    normalized_query: str


class SkillProfilePayload(BaseModel):
    title: str | None = None
    parent_skill_id: str | None = None
    summary: str | None = None
    local_app_name: str | None = None
    local_app_installed: bool | None = None
    launch_target: str | None = None
    open_supported: bool | None = None
    local_notes: str | None = None
    api_provider: str | None = None
    api_configured: bool | None = None
    api_scopes: list[str] = []
    api_notes: str | None = None
    notes: str | None = None
    tags: list[str] = []
    linked_intents: list[str] = []
    custom_fields: dict[str, str] = {}


class SkillProfileCreateRequest(SkillProfilePayload):
    skill_id: str


class ActionMapPayload(BaseModel):
    title: str | None = None
    description: str | None = None
    trigger_query: str | None = None
    notes: str | None = None
    tags: list[str] = []
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []


class ActionMapCreateRequest(ActionMapPayload):
    map_id: str


class KbStatusResponse(BaseModel):
    path: str
    exists: bool
    doc_count: int
    chunk_count: int
    embedding_count: int
    total_size_bytes: int
    last_indexed: str | None


class KbValidateRequest(BaseModel):
    path: str = Field(max_length=4096)


class KbValidateResponse(BaseModel):
    path: str
    exists: bool
    is_directory: bool
    readable: bool
    file_count: int
    error: str | None = None


class KbChangeRequest(BaseModel):
    path: str = Field(max_length=4096)


class KbChangeResponse(BaseModel):
    started: bool
    previous_path: str
    new_path: str
    indexing: dict[str, object]
    message: str


def _require_service():
    """Get service or raise 503 if not yet initialized."""
    svc = _get_service()
    if svc is None:
        raise HTTPException(status_code=503, detail="Backend is starting up, please wait...")
    return svc


class FeedbackRequest(BaseModel):
    query_text: str
    feedback_type: str  # 'positive', 'negative'
    citation_paths: list[str] = []
    session_id: str = ""


class FeedbackResponse(BaseModel):
    ok: bool
    feedback_id: str = ""


# HTTP Endpoints

@app.post("/api/feedback", response_model=FeedbackResponse)
def submit_feedback(request: FeedbackRequest) -> FeedbackResponse:
    """Record user feedback (thumbs up/down) for search quality learning."""
    import json
    import uuid
    from jarvis.app.bootstrap import init_database
    from jarvis.app.config import JarvisConfig
    from jarvis.runtime_paths import resolve_menubar_data_dir

    feedback_id = str(uuid.uuid4())
    try:
        db = init_database(JarvisConfig(data_dir=resolve_menubar_data_dir()))
        relevant = request.citation_paths if request.feedback_type == "positive" else []
        irrelevant = request.citation_paths if request.feedback_type == "negative" else []
        db.execute(
            "INSERT INTO search_feedback "
            "(feedback_id, query_text, feedback_type, relevant_paths, irrelevant_paths, citation_paths, session_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                feedback_id,
                request.query_text,
                request.feedback_type,
                json.dumps(relevant),
                json.dumps(irrelevant),
                json.dumps(request.citation_paths),
                request.session_id,
            ),
        )
        db.commit()
        db.close()
    except Exception:
        return FeedbackResponse(ok=False)

    # Trigger affinity update for positive feedback
    if request.feedback_type == "positive" and request.citation_paths:
        try:
            _update_query_document_affinity(request.query_text, request.citation_paths)
        except Exception:
            pass

    return FeedbackResponse(ok=True, feedback_id=feedback_id)


def _update_query_document_affinity(query_text: str, doc_paths: list[str]) -> None:
    """Update query-document affinity scores based on positive feedback."""
    import re
    from jarvis.app.bootstrap import init_database
    from jarvis.app.config import JarvisConfig
    from jarvis.runtime_paths import resolve_menubar_data_dir

    # Extract a normalized query pattern (lowercase, stripped of particles)
    pattern = query_text.lower().strip()
    pattern = re.sub(r'[.,!?·…~]', ' ', pattern)
    pattern = ' '.join(w for w in pattern.split() if len(w) >= 2)
    if not pattern:
        return

    db = init_database(JarvisConfig(data_dir=resolve_menubar_data_dir()))
    for path in doc_paths:
        db.execute(
            "INSERT INTO query_document_affinity (query_pattern, document_path, affinity_score, hit_count) "
            "VALUES (?, ?, 0.5, 1) "
            "ON CONFLICT(query_pattern, document_path) DO UPDATE SET "
            "affinity_score = min(1.0, affinity_score + 0.1), "
            "hit_count = hit_count + 1, "
            "last_updated = unixepoch()",
            (pattern, path),
        )
    db.commit()
    db.close()


@app.post("/api/ask", response_model=AskResponse)
def ask(request: AskRequest) -> AskResponse:
    """Process a text query and return JARVIS response.

    NOTE: This is a sync ``def`` endpoint (not ``async def``) so that
    FastAPI runs it in a thread-pool worker.  The underlying
    ``service.handle()`` call is blocking (LLM inference can take 30-40 s)
    and would freeze the entire event loop if called from an ``async``
    handler, making health-checks and other requests unresponsive.
    """
    payload: dict[str, object] = {"text": request.text}
    if request.context_document_paths:
        payload["context_document_paths"] = request.context_document_paths
    rpc_request = RpcRequest(
        request_id=str(uuid.uuid4()),
        session_id=request.session_id,
        request_type="ask_text",
        payload=payload,
    )
    rpc_response: RpcResponse = _require_service().handle(rpc_request)

    if not rpc_response.ok:
        raise HTTPException(
            status_code=400,
            detail=rpc_response.error.message if rpc_response.error else "Unknown error",
        )

    return AskResponse(**rpc_response.payload)


# ── Cached health data (updated in background) ─────────────
_cached_health: dict[str, object] = {
    "healthy": False,
    "message": "Backend is starting up...",
    "checks": {},
    "details": {},
    "status_level": "starting",
    "chunk_count": 0,
    "doc_count": 0,
    "failed_doc_count": 0,
    "total_size_bytes": 0,
    "embedding_count": 0,
}
_health_refresh_lock = threading.Lock()


def _refresh_health_cache() -> None:
    """Refresh cached health data in background — never blocks the API thread."""
    if not _health_refresh_lock.acquire(blocking=False):
        return  # another refresh already running
    try:
        svc = _get_service()
        if svc is None:
            return
        rpc_request = RpcRequest(
            request_id=str(uuid.uuid4()),
            session_id="health-check",
            request_type="health",
            payload={},
        )
        rpc_response: RpcResponse = svc.handle(rpc_request)
        health_data = rpc_response.payload.get("health", {})
        _cached_health.update(health_data)
        _auto_detect_new_files(health_data)
    except Exception as exc:
        logger.warning("Health refresh failed: %s", exc)
    finally:
        _health_refresh_lock.release()


def _start_health_refresh_loop() -> None:
    """Periodically refresh health cache every 10s."""
    while True:
        _time.sleep(10)
        _refresh_health_cache()


threading.Thread(target=_start_health_refresh_loop, daemon=True, name="health-refresh").start()


@app.get("/api/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Return cached health status — always responds instantly, never blocks."""
    result = dict(_cached_health)
    result["indexing"] = _get_index_state()
    return HealthResponse(health=result)


@app.post("/api/reindex")
def reindex(request: Request):
    """Trigger a knowledge base reindex."""
    _check_origin(request)
    started = _trigger_reindex(auto=False)
    return {
        "started": started,
        "indexing": _get_index_state(),
    }


@app.get("/api/kb/status", response_model=KbStatusResponse)
def kb_status() -> KbStatusResponse:
    """Return current knowledge base directory status."""
    kb_path = _resolve_kb_root()
    path_str = str(kb_path) if kb_path else ""
    exists = kb_path is not None and kb_path.exists()

    health = dict(_cached_health)
    return KbStatusResponse(
        path=path_str,
        exists=exists,
        doc_count=int(health.get("doc_count", 0)),
        chunk_count=int(health.get("chunk_count", 0)),
        embedding_count=int(health.get("embedding_count", 0)),
        total_size_bytes=int(health.get("total_size_bytes", 0)),
        last_indexed=_index_state.get("last_completed"),
    )


@app.post("/api/kb/validate", response_model=KbValidateResponse)
def kb_validate(request: KbValidateRequest) -> KbValidateResponse:
    """Validate a candidate knowledge base path before committing."""
    from jarvis.app.runtime_context import is_indexable

    raw_path = request.path.strip()
    if not raw_path:
        return KbValidateResponse(
            path=raw_path, exists=False, is_directory=False,
            readable=False, file_count=0, error="경로가 비어 있습니다.",
        )

    p = Path(raw_path).expanduser().resolve()
    if not p.exists():
        return KbValidateResponse(
            path=str(p), exists=False, is_directory=False,
            readable=False, file_count=0, error="경로가 존재하지 않습니다.",
        )
    if not p.is_dir():
        return KbValidateResponse(
            path=str(p), exists=True, is_directory=False,
            readable=False, file_count=0, error="디렉토리가 아닙니다.",
        )
    if not os.access(p, os.R_OK):
        return KbValidateResponse(
            path=str(p), exists=True, is_directory=True,
            readable=False, file_count=0, error="읽기 권한이 없습니다.",
        )

    file_count = sum(1 for f in p.rglob("*") if f.is_file() and is_indexable(f))
    return KbValidateResponse(
        path=str(p), exists=True, is_directory=True,
        readable=True, file_count=file_count, error=None,
    )


@app.post("/api/kb/change", response_model=KbChangeResponse)
def kb_change(http_request: Request, request: KbChangeRequest) -> KbChangeResponse:
    """Change the knowledge base directory. Purges old index and triggers re-indexing."""
    _check_origin(http_request)

    from jarvis.app.runtime_context import is_indexable

    new_path = Path(request.path.strip()).expanduser().resolve()

    # Validate
    if not new_path.is_dir():
        raise HTTPException(status_code=400, detail="유효한 디렉토리가 아닙니다.")
    if not os.access(new_path, os.R_OK):
        raise HTTPException(status_code=400, detail="읽기 권한이 없습니다.")

    previous_path = str(_resolve_kb_root() or "")

    # Set environment variable so all subsequent resolves use the new path
    os.environ["JARVIS_KNOWLEDGE_BASE"] = str(new_path)

    # Purge old indexed data and trigger full reindex
    def _purge_and_reindex() -> None:
        from jarvis.app.bootstrap import init_database
        from jarvis.app.config import JarvisConfig
        from jarvis.app.runtime_context import (
            purge_documents_outside_knowledge_base,
            run_indexing,
        )
        from jarvis.cli.menu_bridge import resolve_menubar_data_dir

        db = None
        try:
            _index_state["status"] = "scanning"
            _index_state["processed"] = 0
            _index_state["total"] = 0
            _index_state["error"] = None

            data_dir = resolve_menubar_data_dir()
            config = JarvisConfig(
                data_dir=data_dir,
                watched_folders=[new_path],
            )
            db = init_database(config)

            # Purge documents from previous KB path
            purge_documents_outside_knowledge_base(db, new_path)

            # Count indexable files
            files = [f for f in new_path.rglob("*") if f.is_file() and is_indexable(f)]
            _index_state["total"] = len(files)
            _index_state["status"] = "indexing"

            progress = {"count": 0}

            def _reporter(msg: str) -> None:
                if "Indexing " in msg and "/" in msg:
                    progress["count"] += 1
                    _index_state["processed"] = progress["count"]

            run_indexing(
                db,
                new_path,
                data_dir=data_dir,
                start_background_backfill=True,
                reporter=_reporter,
            )

            _index_state["status"] = "done"
            _index_state["last_completed"] = _time.strftime("%Y-%m-%dT%H:%M:%S")
            logger.info("KB change reindex complete: %s -> %s", previous_path, new_path)
        except Exception as exc:
            _index_state["status"] = "error"
            _index_state["error"] = str(exc)
            logger.error("KB change reindex failed: %s", exc)
        finally:
            if db is not None:
                db.close()
            _index_lock.release()

    # Acquire the index lock — fail if already indexing
    if not _index_lock.acquire(blocking=False):
        raise HTTPException(status_code=409, detail="인덱싱이 진행 중입니다. 완료 후 다시 시도해주세요.")

    threading.Thread(target=_purge_and_reindex, daemon=True, name="kb-change-worker").start()

    # Return snapshot without calling _get_index_state() (which would deadlock
    # because we already hold _index_lock and threading.Lock is not reentrant).
    return KbChangeResponse(
        started=True,
        previous_path=previous_path,
        new_path=str(new_path),
        indexing=dict(_index_state),
        message="지식기반 디렉토리가 변경되었습니다. 재인덱싱을 시작합니다.",
    )


@app.post("/api/restart")
def restart_server(request: Request):
    """Restart the backend process. Responds immediately, then replaces the process."""
    _check_origin(request)

    def _do_restart() -> None:
        _time.sleep(0.5)  # let the HTTP response flush
        logger.info("Restarting backend process via os.execv...")
        # Update PID file if it exists (start.sh writes .pids/backend.pid)
        pid_file = Path(__file__).resolve().parent.parent.parent.parent / "ProjectHub-terminal-architect" / ".pids" / "backend.pid"
        if pid_file.exists():
            try:
                pid_file.write_text(str(os.getpid()))
            except Exception:
                pass
        os.execv(sys.executable, [sys.executable] + sys.argv)

    threading.Thread(target=_do_restart, daemon=True, name="restart").start()
    return {"restarting": True}


@app.post("/api/normalize", response_model=NormalizeResponse)
def normalize_query(request: NormalizeRequest) -> NormalizeResponse:
    """Normalize a Korean query."""
    rpc_request = RpcRequest(
        request_id=str(uuid.uuid4()),
        session_id="normalize",
        request_type="normalize_query",
        payload={"text": request.text},
    )
    rpc_response: RpcResponse = _require_service().handle(rpc_request)

    if not rpc_response.ok:
        raise HTTPException(
            status_code=400,
            detail=rpc_response.error.message if rpc_response.error else "Unknown error",
        )

    return NormalizeResponse(**rpc_response.payload)


@app.get("/api/runtime-state")
def runtime_state():
    """Get full runtime state."""
    rpc_request = RpcRequest(
        request_id=str(uuid.uuid4()),
        session_id="runtime-state",
        request_type="runtime_state",
        payload={},
    )
    rpc_response: RpcResponse = _require_service().handle(rpc_request)

    if not rpc_response.ok:
        raise HTTPException(
            status_code=400,
            detail=rpc_response.error.message if rpc_response.error else "Unknown error",
        )

    return rpc_response.payload


def _skill_store():
    from jarvis.service.intent_skill_store import (
        build_skill_catalog,
        create_action_map,
        create_skill_profile,
        list_action_maps,
        upsert_action_map,
        upsert_skill_profile,
    )
    return build_skill_catalog, create_skill_profile, upsert_skill_profile, list_action_maps, create_action_map, upsert_action_map


@app.get("/api/skills")
def skills_catalog() -> dict[str, Any]:
    build_skill_catalog, *_ = _skill_store()
    return {"catalog": build_skill_catalog()}


@app.post("/api/skills")
def create_skill(request: SkillProfileCreateRequest) -> dict[str, Any]:
    build_skill_catalog, create_skill_profile_fn, *_ = _skill_store()
    try:
        profile = create_skill_profile_fn(request.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"profile": profile, "catalog": build_skill_catalog()}


@app.put("/api/skills/{skill_id}")
def update_skill(skill_id: str, request: SkillProfilePayload) -> dict[str, Any]:
    build_skill_catalog, _, upsert_skill_profile_fn, *_ = _skill_store()
    try:
        profile = upsert_skill_profile_fn(skill_id, request.model_dump(exclude_none=False))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"profile": profile, "catalog": build_skill_catalog()}


@app.get("/api/action-maps")
def action_maps() -> dict[str, Any]:
    *_, list_action_maps_fn, _, _ = _skill_store()
    return {"maps": list_action_maps_fn()}


@app.post("/api/action-maps")
def create_map(request: ActionMapCreateRequest) -> dict[str, Any]:
    *_, list_action_maps_fn, create_action_map_fn, _ = _skill_store()
    try:
        action_map = create_action_map_fn(request.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"action_map": action_map, "maps": list_action_maps_fn()}


@app.put("/api/action-maps/{map_id}")
def update_map(map_id: str, request: ActionMapPayload) -> dict[str, Any]:
    *_, list_action_maps_fn, _, upsert_action_map_fn = _skill_store()
    try:
        action_map = upsert_action_map_fn(map_id, request.model_dump(exclude_none=False))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"action_map": action_map, "maps": list_action_maps_fn()}


def _resolve_kb_root() -> Path | None:
    """Resolve knowledge base root path."""
    kb_env = os.environ.get("JARVIS_KNOWLEDGE_BASE")
    if kb_env:
        p = Path(kb_env)
        if p.is_dir():
            return p
    from jarvis.app.runtime_context import resolve_knowledge_base_path
    return resolve_knowledge_base_path()


class BrowseEntry(BaseModel):
    name: str
    path: str
    type: str  # "file" or "directory"
    extension: str | None = None
    size: int | None = None


class BrowseResponse(BaseModel):
    path: str
    entries: list[BrowseEntry]


@app.get("/api/browse", response_model=BrowseResponse)
def browse_directory(path: str = ""):
    """List directory contents within the knowledge base."""
    kb_root = _resolve_kb_root()
    if kb_root is None:
        raise HTTPException(status_code=500, detail="Knowledge base path not configured")

    target = (kb_root / path).resolve()

    # Security: ensure path is within knowledge base
    try:
        target.relative_to(kb_root.resolve())
    except ValueError:
        raise HTTPException(status_code=403, detail="Access denied: path outside knowledge base")

    if not target.exists():
        raise HTTPException(status_code=404, detail=f"Path not found: {path}")

    if not target.is_dir():
        raise HTTPException(status_code=400, detail=f"Not a directory: {path}")

    entries: list[BrowseEntry] = []
    for item in sorted(target.iterdir(), key=lambda p: (p.is_file(), p.name.lower())):
        if item.name.startswith("."):
            continue
        rel_path = str(item.relative_to(kb_root.resolve()))
        if item.is_dir():
            entries.append(BrowseEntry(name=item.name, path=rel_path, type="directory"))
        else:
            stat = item.stat()
            entries.append(BrowseEntry(
                name=item.name,
                path=rel_path,
                type="file",
                extension=item.suffix.lower() if item.suffix else None,
                size=stat.st_size,
            ))

    return BrowseResponse(path=path, entries=entries)


@app.get("/api/search-docs")
def search_documents(q: str = Query(..., min_length=1, max_length=200)):
    """Search indexed documents by filename, path, or content keywords."""
    kb_root = _resolve_kb_root()
    from jarvis.app.bootstrap import init_database
    from jarvis.app.config import JarvisConfig
    from jarvis.runtime_paths import resolve_menubar_data_dir

    data_dir = resolve_menubar_data_dir()
    db = init_database(JarvisConfig(data_dir=data_dir))

    try:
        terms = q.lower().split()

        # 1) Path/filename match
        all_docs = db.execute(
            "SELECT document_id, path, size_bytes, indexing_status FROM documents "
            "WHERE indexing_status IN ('INDEXED', 'FAILED') ORDER BY path"
        ).fetchall()

        path_matches = []
        for doc_id, doc_path, size_bytes, status in all_docs:
            path_lower = doc_path.lower()
            hits = sum(1 for t in terms if t in path_lower)
            if hits == 0:
                continue
            rel = doc_path
            if kb_root:
                try:
                    rel = str(Path(doc_path).relative_to(kb_root.resolve()))
                except ValueError:
                    pass
            chunk_count = db.execute(
                "SELECT COUNT(*) FROM chunks WHERE document_id = ?", (doc_id,)
            ).fetchone()[0]
            path_matches.append({
                "document_id": doc_id,
                "path": rel,
                "full_path": doc_path,
                "name": Path(doc_path).name,
                "size_bytes": size_bytes,
                "chunk_count": chunk_count,
                "status": status,
                "match_type": "path",
                "_score": hits,
            })
        path_matches.sort(key=lambda m: (-m["_score"], m["path"]))
        for m in path_matches:
            del m["_score"]

        # 2) FTS content match (top 10 documents by chunk hits)
        fts_query = " AND ".join(f'"{t}"' for t in terms if len(t) >= 2)
        content_matches = []
        if fts_query:
            try:
                fts_rows = db.execute(
                    "SELECT c.document_id, COUNT(*) as hits "
                    "FROM chunks_fts fts "
                    "JOIN chunks c ON c.rowid = fts.rowid "
                    "WHERE chunks_fts MATCH ? "
                    "GROUP BY c.document_id ORDER BY hits DESC LIMIT 10",
                    (fts_query,),
                ).fetchall()
                matched_doc_ids = {m["document_id"] for m in path_matches}
                for doc_id, hits in fts_rows:
                    if doc_id in matched_doc_ids:
                        continue
                    doc_row = db.execute(
                        "SELECT path, size_bytes, indexing_status FROM documents WHERE document_id = ?",
                        (doc_id,),
                    ).fetchone()
                    if not doc_row:
                        continue
                    doc_path, size_bytes, status = doc_row
                    rel = doc_path
                    if kb_root:
                        try:
                            rel = str(Path(doc_path).relative_to(kb_root.resolve()))
                        except ValueError:
                            pass
                    content_matches.append({
                        "document_id": doc_id,
                        "path": rel,
                        "full_path": doc_path,
                        "name": Path(doc_path).name,
                        "size_bytes": size_bytes,
                        "chunk_count": hits,
                        "status": status,
                        "match_type": "content",
                    })
            except Exception:
                pass  # FTS match syntax error — skip

        return {"query": q, "results": path_matches + content_matches}
    finally:
        db.close()


# ---- Learned Patterns Management ----

class LearnedPatternSummary(BaseModel):
    pattern_id: str
    canonical_query: str
    failed_variants: list[str]
    retrieval_task: str
    entity_hints: dict
    reformulation_type: str
    success_count: int
    citation_paths: list[str]
    created_at: int
    last_used_at: int


class LearnedPatternsResponse(BaseModel):
    patterns: list[LearnedPatternSummary]
    total: int


def _learning_db_connection():
    """Open a fresh SQLite connection to the jarvis.db file."""
    import sqlite3
    kb_root = _resolve_kb_root()
    if kb_root is None:
        return None
    # jarvis.db is at ~/.jarvis-menubar/jarvis.db (parent of knowledge_base)
    db_path = kb_root.parent / ".jarvis-menubar" / "jarvis.db"
    if not db_path.exists():
        return None
    return sqlite3.connect(str(db_path))


@app.get("/api/learned-patterns", response_model=LearnedPatternsResponse)
def list_learned_patterns(retrieval_task: str | None = None):
    """List all learned patterns, optionally filtered by retrieval_task."""
    import json
    conn = _learning_db_connection()
    if conn is None:
        return LearnedPatternsResponse(patterns=[], total=0)
    try:
        query = (
            "SELECT pattern_id, canonical_query, failed_variants, retrieval_task, "
            "entity_hints_json, reformulation_type, success_count, citation_paths, "
            "created_at, last_used_at FROM learned_patterns"
        )
        params: tuple = ()
        if retrieval_task:
            query += " WHERE retrieval_task = ?"
            params = (retrieval_task,)
        query += " ORDER BY success_count DESC, last_used_at DESC"
        rows = conn.execute(query, params).fetchall()
        summaries = [
            LearnedPatternSummary(
                pattern_id=r[0],
                canonical_query=r[1],
                failed_variants=json.loads(r[2] or "[]"),
                retrieval_task=r[3],
                entity_hints=json.loads(r[4] or "{}"),
                reformulation_type=r[5],
                success_count=r[6],
                citation_paths=[Path(p).name for p in json.loads(r[7] or "[]")],
                created_at=r[8],
                last_used_at=r[9],
            )
            for r in rows
        ]
        return LearnedPatternsResponse(patterns=summaries, total=len(summaries))
    finally:
        conn.close()


class VisionAskResponse(BaseModel):
    answer: str
    model_id: str
    elapsed_ms: int


_vision_backend_cache: dict[str, object] = {}


def _get_vision_backend(model_alias: str = "gemma4:e4b"):
    """Lazy-load GemmaVlmBackend (cached across requests)."""
    cached = _vision_backend_cache.get(model_alias)
    if cached is not None:
        return cached
    from jarvis.runtime.gemma_vlm_backend import GemmaVlmBackend
    from jarvis.contracts import RuntimeDecision
    backend = GemmaVlmBackend()
    decision = RuntimeDecision(
        tier="deep",
        backend="mlx",
        model_id=model_alias,
        context_window=131072,
    )
    backend.load(decision)
    _vision_backend_cache[model_alias] = backend
    return backend


@app.post("/api/ask/vision", response_model=VisionAskResponse)
async def ask_vision(
    request: Request,
    text: str = Form(...),
    image: UploadFile = File(...),
    model: str = Form("gemma4:e4b"),
):
    """Answer a question about an uploaded image using Gemma 4 vision model."""
    _check_origin(request)
    import tempfile
    import time as _time

    # Validate image type
    allowed_ext = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}
    filename = image.filename or "upload"
    ext = Path(filename).suffix.lower()
    if ext not in allowed_ext:
        raise HTTPException(status_code=400, detail=f"Unsupported image type: {ext}")

    # Save to temp file (mlx_vlm requires a file path)
    content = await image.read()
    if len(content) > 20 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Image too large (max 20MB)")

    # Validate image magic bytes
    _IMAGE_MAGIC = {
        b'\x89PNG': '.png',
        b'\xff\xd8\xff': '.jpg',
        b'GIF87a': '.gif',
        b'GIF89a': '.gif',
        b'RIFF': '.webp',  # WebP starts with RIFF
        b'BM': '.bmp',
    }
    header = content[:8]
    magic_matched = any(header.startswith(m) for m in _IMAGE_MAGIC)
    if not magic_matched:
        raise HTTPException(status_code=400, detail="Invalid image content: magic bytes don't match an image format")

    with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    _ALLOWED_VISION_MODELS = {"gemma4:e4b", "gemma4:e2b"}
    if model not in _ALLOWED_VISION_MODELS:
        raise HTTPException(status_code=400, detail=f"Unsupported vision model: {model}")

    def _run_vision_sync():
        backend = _get_vision_backend(model)
        t0 = _time.perf_counter()
        answer = backend.generate_with_image(prompt=text, image_path=tmp_path)
        elapsed_ms = int((_time.perf_counter() - t0) * 1000)
        return VisionAskResponse(
            answer=answer,
            model_id=backend.model_id,
            elapsed_ms=elapsed_ms,
        )

    try:
        return await asyncio.to_thread(_run_vision_sync)
    finally:
        try:
            Path(tmp_path).unlink()
        except Exception:
            pass


class ExtractedTextChunk(BaseModel):
    chunk_id: str
    text: str
    heading_path: str


class ExtractedTextResponse(BaseModel):
    path: str
    document_id: str
    total_chunks: int
    chunks: list[ExtractedTextChunk]


@app.get("/api/file/extracted", response_model=ExtractedTextResponse)
def get_extracted_text(path: str, limit: int = Query(default=200, ge=1, le=1000)):
    """Return indexed/extracted text chunks for binary documents (HWP, DOCX, PDF, etc.)."""
    kb_root = _resolve_kb_root()
    if kb_root is None:
        raise HTTPException(status_code=500, detail="Knowledge base path not configured")

    # Resolve absolute path for document lookup
    raw_path = Path(path).expanduser()
    if not raw_path.is_absolute():
        abs_path = str((kb_root / raw_path).resolve())
    else:
        abs_path = str(raw_path.resolve())

    # Security: ensure path is within knowledge base (same as /api/file)
    try:
        Path(abs_path).relative_to(kb_root.resolve())
    except ValueError:
        raise HTTPException(status_code=403, detail="Access denied: path outside knowledge base")

    conn = _learning_db_connection()
    if conn is None:
        raise HTTPException(status_code=500, detail="Database unavailable")
    try:
        import unicodedata as _unicodedata
        # macOS stores filesystem paths in NFD; incoming request may be NFC.
        # Try multiple normalizations to match what the indexer wrote.
        candidates = []
        seen = set()
        for form in ("NFC", "NFD", None):
            variant = _unicodedata.normalize(form, abs_path) if form else abs_path
            if variant not in seen:
                seen.add(variant)
                candidates.append(variant)

        doc_row = None
        for variant in candidates:
            doc_row = conn.execute(
                "SELECT document_id FROM documents WHERE path = ?",
                (variant,),
            ).fetchone()
            if doc_row is not None:
                break
        if doc_row is None:
            raise HTTPException(status_code=404, detail=f"Document not indexed: {path}")

        document_id = doc_row[0]
        total = conn.execute(
            "SELECT COUNT(*) FROM chunks WHERE document_id = ?",
            (document_id,),
        ).fetchone()[0]

        rows = conn.execute(
            "SELECT chunk_id, text, heading_path FROM chunks "
            "WHERE document_id = ? ORDER BY line_start, byte_start LIMIT ?",
            (document_id, limit),
        ).fetchall()
        chunks = [
            ExtractedTextChunk(
                chunk_id=r[0],
                text=r[1] or "",
                heading_path=r[2] or "",
            )
            for r in rows
        ]
        return ExtractedTextResponse(
            path=path,
            document_id=document_id,
            total_chunks=total,
            chunks=chunks,
        )
    finally:
        conn.close()


class ForgetPatternRequest(BaseModel):
    pattern_id: str | None = None  # if None, delete all patterns


@app.post("/api/learned-patterns/forget")
def forget_learned_patterns(http_request: Request, request: ForgetPatternRequest):
    """Delete a specific learned pattern, or all patterns if pattern_id is None."""
    _check_origin(http_request)
    conn = _learning_db_connection()
    if conn is None:
        raise HTTPException(status_code=500, detail="Knowledge base path not configured")
    try:
        if request.pattern_id:
            result = conn.execute(
                "DELETE FROM learned_patterns WHERE pattern_id = ?",
                (request.pattern_id,),
            )
        else:
            result = conn.execute("DELETE FROM learned_patterns")
        conn.commit()
        deleted = result.rowcount
        return {"deleted": deleted}
    finally:
        conn.close()


class ForgetDataRequest(BaseModel):
    scope: str = Field(default="all", pattern="^(all|conversations|session_events|task_logs)$")


@app.post("/api/data/forget")
def forget_user_data(http_request: Request, request: ForgetDataRequest):
    """Delete user data: conversations, session events, task logs, or all."""
    _check_origin(http_request)
    conn = _learning_db_connection()
    if conn is None:
        raise HTTPException(status_code=500, detail="Database unavailable")
    try:
        deleted = {}
        if request.scope in ("all", "conversations"):
            r = conn.execute("DELETE FROM conversation_turns")
            deleted["conversation_turns"] = r.rowcount
        if request.scope in ("all", "session_events"):
            r = conn.execute("DELETE FROM session_events")
            deleted["session_events"] = r.rowcount
        if request.scope in ("all", "task_logs"):
            r = conn.execute("DELETE FROM task_logs")
            deleted["task_logs"] = r.rowcount
        if request.scope == "all":
            r = conn.execute("DELETE FROM learned_patterns")
            deleted["learned_patterns"] = r.rowcount
        conn.commit()
        return {"deleted": deleted, "scope": request.scope}
    finally:
        conn.close()


@app.get("/api/file")
def serve_file(path: str):
    """Serve a file from allowed directories.

    Validates that the requested path is within the knowledge_base
    directory before serving.
    """
    raw_path = Path(path).expanduser()

    # Resolve knowledge_base root
    kb_root = _resolve_kb_root()

    # If path is relative (e.g. "file.xlsx"), resolve against knowledge_base
    if not raw_path.is_absolute() and kb_root:
        file_path = (kb_root / raw_path).resolve()
    else:
        file_path = raw_path.resolve()

    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail=f"File not found: {file_path.name}")

    # Security: validate that file is within knowledge_base
    if kb_root is None:
        raise HTTPException(status_code=403, detail="No allowed directories configured")

    try:
        file_path.relative_to(kb_root.resolve())
    except ValueError:
        raise HTTPException(status_code=403, detail="Path outside allowed scope")

    # Determine content type
    content_type, _ = mimetypes.guess_type(str(file_path))
    if content_type is None:
        content_type = "application/octet-stream"

    # For text files, detect encoding and serve as UTF-8
    _TEXT_TYPES = {
        "text/", "application/json", "application/xml",
        "application/sql", "application/javascript",
    }
    _TEXT_EXTS = {
        ".sql", ".txt", ".csv", ".tsv", ".log", ".md", ".rst",
        ".py", ".js", ".ts", ".tsx", ".jsx", ".html", ".htm", ".css",
        ".yaml", ".yml", ".json", ".xml", ".toml", ".cfg", ".ini",
        ".sh", ".bash", ".zsh", ".java", ".go", ".rs", ".swift",
        ".kt", ".rb", ".c", ".cpp", ".h",
    }
    suffix = file_path.suffix.lower()
    is_text = any(content_type.startswith(t) for t in _TEXT_TYPES) or suffix in _TEXT_EXTS

    if is_text:
        raw = file_path.read_bytes()
        # Try multiple encodings (same as ReadFileTool)
        decoded = None
        detected_encoding = "unknown"
        for encoding in ("utf-8", "utf-8-sig", "cp949", "euc-kr", "utf-16", "latin-1"):
            try:
                decoded = raw.decode(encoding)
                detected_encoding = encoding
                break
            except (UnicodeDecodeError, UnicodeError):
                continue
        if decoded is not None:
            from fastapi.responses import Response
            return Response(
                content=decoded,
                media_type=f"{content_type}; charset=utf-8",
                headers={
                    "Content-Disposition": f'inline; filename="{file_path.name}"',
                    "X-Detected-Encoding": detected_encoding,
                    "X-File-Size": str(len(raw)),
                    "Access-Control-Expose-Headers": "X-Detected-Encoding, X-File-Size",
                },
            )

    return FileResponse(
        path=str(file_path),
        media_type=content_type,
        filename=file_path.name,
    )


# WebSocket endpoint for real-time communication
@app.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str) -> None:
    """WebSocket endpoint for real-time bidirectional communication."""
    await websocket.accept()
    
    try:
        while True:
            # Receive message from client
            data = await websocket.receive_text()
            
            try:
                import json
                payload = json.loads(data)
                
                # Create RPC request
                rpc_request = RpcRequest(
                    request_id=str(uuid.uuid4()),
                    session_id=session_id,
                    request_type=payload.get("request_type", "ask_text"),
                    payload=payload.get("payload", {}),
                )
                
                # Handle request
                rpc_response: RpcResponse = _require_service().handle(rpc_request)
                
                # Send response
                if rpc_response.ok:
                    await websocket.send_json(rpc_response.payload)
                else:
                    await websocket.send_json({
                        "error": rpc_response.error.message if rpc_response.error else "Unknown error",
                    })
                    
            except json.JSONDecodeError:
                await websocket.send_json({
                    "error": "Invalid JSON format",
                })
            except Exception as e:
                import logging
                logging.getLogger(__name__).exception("WebSocket handler error: session=%s", session_id)
                await websocket.send_json({
                    "error": "Internal server error",
                })
                
    except WebSocketDisconnect:
        # Client disconnected normally
        pass
    except Exception as e:
        # Handle unexpected errors
        try:
            await websocket.close(code=1011, reason=str(e))
        except Exception:
            pass


def main() -> int:
    """Run the FastAPI server using uvicorn."""
    import uvicorn
    
    parser = argparse.ArgumentParser(description="JARVIS Web API Server")
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Host to bind to (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port to bind to (default: 8000)",
    )
    parser.add_argument(
        "--reload",
        action="store_true",
        help="Enable auto-reload for development",
    )
    
    args = parser.parse_args()
    
    uvicorn.run(
        "jarvis.web_api:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
    )
    
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
