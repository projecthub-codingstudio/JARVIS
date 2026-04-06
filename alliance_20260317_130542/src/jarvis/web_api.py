"""FastAPI bridge for web UI integration."""

from __future__ import annotations

import mimetypes
import os
import uuid
import argparse
from pathlib import Path
from typing import Any

from fastapi import FastAPI, WebSocket, HTTPException, WebSocketDisconnect, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from jarvis.service.application import JarvisApplicationService
from jarvis.service.intent_skill_store import (
    build_skill_catalog,
    create_action_map,
    create_skill_profile,
    list_action_maps,
    upsert_action_map,
    upsert_skill_profile,
)
from jarvis.service.protocol import RpcRequest, RpcResponse


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

service = JarvisApplicationService()


# Request/Response models
class AskRequest(BaseModel):
    text: str = Field(max_length=16000)
    session_id: str = Field(max_length=128)


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


# HTTP Endpoints
@app.post("/api/ask", response_model=AskResponse)
async def ask(request: AskRequest) -> AskResponse:
    """Process a text query and return JARVIS response."""
    rpc_request = RpcRequest(
        request_id=str(uuid.uuid4()),
        session_id=request.session_id,
        request_type="ask_text",
        payload={"text": request.text},
    )
    rpc_response: RpcResponse = service.handle(rpc_request)
    
    if not rpc_response.ok:
        raise HTTPException(
            status_code=400,
            detail=rpc_response.error.message if rpc_response.error else "Unknown error",
        )
    
    return AskResponse(**rpc_response.payload)


@app.get("/api/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Check JARVIS backend health status."""
    rpc_request = RpcRequest(
        request_id=str(uuid.uuid4()),
        session_id="health-check",
        request_type="health",
        payload={},
    )
    rpc_response: RpcResponse = service.handle(rpc_request)
    return HealthResponse(**rpc_response.payload)


@app.post("/api/normalize", response_model=NormalizeResponse)
async def normalize_query(request: NormalizeRequest) -> NormalizeResponse:
    """Normalize a Korean query."""
    rpc_request = RpcRequest(
        request_id=str(uuid.uuid4()),
        session_id="normalize",
        request_type="normalize_query",
        payload={"text": request.text},
    )
    rpc_response: RpcResponse = service.handle(rpc_request)
    
    if not rpc_response.ok:
        raise HTTPException(
            status_code=400,
            detail=rpc_response.error.message if rpc_response.error else "Unknown error",
        )
    
    return NormalizeResponse(**rpc_response.payload)


@app.get("/api/runtime-state")
async def runtime_state():
    """Get full runtime state."""
    rpc_request = RpcRequest(
        request_id=str(uuid.uuid4()),
        session_id="runtime-state",
        request_type="runtime_state",
        payload={},
    )
    rpc_response: RpcResponse = service.handle(rpc_request)
    
    if not rpc_response.ok:
        raise HTTPException(
            status_code=400,
            detail=rpc_response.error.message if rpc_response.error else "Unknown error",
        )
    
    return rpc_response.payload


@app.get("/api/skills")
async def skills_catalog() -> dict[str, Any]:
    return {"catalog": build_skill_catalog()}


@app.post("/api/skills")
async def create_skill(request: SkillProfileCreateRequest) -> dict[str, Any]:
    try:
        profile = create_skill_profile(request.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"profile": profile, "catalog": build_skill_catalog()}


@app.put("/api/skills/{skill_id}")
async def update_skill(skill_id: str, request: SkillProfilePayload) -> dict[str, Any]:
    try:
        profile = upsert_skill_profile(skill_id, request.model_dump(exclude_none=False))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"profile": profile, "catalog": build_skill_catalog()}


@app.get("/api/action-maps")
async def action_maps() -> dict[str, Any]:
    return {"maps": list_action_maps()}


@app.post("/api/action-maps")
async def create_map(request: ActionMapCreateRequest) -> dict[str, Any]:
    try:
        action_map = create_action_map(request.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"action_map": action_map, "maps": list_action_maps()}


@app.put("/api/action-maps/{map_id}")
async def update_map(map_id: str, request: ActionMapPayload) -> dict[str, Any]:
    try:
        action_map = upsert_action_map(map_id, request.model_dump(exclude_none=False))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"action_map": action_map, "maps": list_action_maps()}


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
async def browse_directory(path: str = ""):
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
async def list_learned_patterns(retrieval_task: str | None = None):
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
                citation_paths=json.loads(r[7] or "[]"),
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
    text: str = Form(...),
    image: UploadFile = File(...),
    model: str = Form("gemma4:e4b"),
):
    """Answer a question about an uploaded image using Gemma 4 vision model."""
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

    try:
        backend = _get_vision_backend(model)
        t0 = _time.perf_counter()
        answer = backend.generate_with_image(prompt=text, image_path=tmp_path)
        elapsed_ms = int((_time.perf_counter() - t0) * 1000)
        return VisionAskResponse(
            answer=answer,
            model_id=backend.model_id,
            elapsed_ms=elapsed_ms,
        )
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
async def get_extracted_text(path: str, limit: int = 200):
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
async def forget_learned_patterns(request: ForgetPatternRequest):
    """Delete a specific learned pattern, or all patterns if pattern_id is None."""
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


@app.get("/api/file")
async def serve_file(path: str):
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
                rpc_response: RpcResponse = service.handle(rpc_request)
                
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
