"""FastAPI bridge for web UI integration."""

from __future__ import annotations

import mimetypes
import uuid
import argparse
from pathlib import Path
from typing import Any

from fastapi import FastAPI, WebSocket, HTTPException, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

from jarvis.service.application import JarvisApplicationService
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
    text: str
    session_id: str


class AskResponse(BaseModel):
    response: dict[str, Any]
    answer: dict[str, Any]
    guide: dict[str, Any]


class HealthResponse(BaseModel):
    health: dict[str, Any]


class NormalizeRequest(BaseModel):
    text: str


class NormalizeResponse(BaseModel):
    normalized_query: str


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


@app.get("/api/file")
async def serve_file(path: str):
    """Serve a file from allowed directories.

    Validates that the requested path is within the knowledge_base
    directory before serving.
    """
    import os
    from jarvis.app.runtime_context import resolve_knowledge_base_path

    raw_path = Path(path).expanduser()

    # Resolve knowledge_base root
    kb_root: Path | None = None
    env_kb = os.getenv("JARVIS_KNOWLEDGE_BASE", "").strip()
    if env_kb:
        kb_root = Path(env_kb).expanduser().resolve()
    if kb_root is None:
        try:
            kb_root = resolve_knowledge_base_path()
        except Exception:
            pass

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
                await websocket.send_json({
                    "error": str(e),
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
        default="0.0.0.0",
        help="Host to bind to (default: 0.0.0.0)",
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
