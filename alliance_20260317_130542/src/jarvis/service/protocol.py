"""Transport-agnostic RPC protocol for JARVIS frontends."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
from typing import Any


@dataclass(frozen=True)
class RpcError:
    code: str
    message: str
    retryable: bool = False


@dataclass(frozen=True)
class RpcRequest:
    request_id: str
    session_id: str
    request_type: str
    payload: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_json(cls, raw: str) -> "RpcRequest":
        data = json.loads(raw)
        return cls(
            request_id=str(data["request_id"]),
            session_id=str(data.get("session_id", "")),
            request_type=str(data["request_type"]),
            payload=dict(data.get("payload", {})),
        )

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False)


@dataclass(frozen=True)
class RpcResponse:
    request_id: str
    session_id: str
    ok: bool
    payload: dict[str, Any] = field(default_factory=dict)
    error: RpcError | None = None

    def to_json(self) -> str:
        data = asdict(self)
        return json.dumps(data, ensure_ascii=False)


def ok_response(*, request: RpcRequest, payload: dict[str, Any]) -> RpcResponse:
    return RpcResponse(
        request_id=request.request_id,
        session_id=request.session_id,
        ok=True,
        payload=payload,
    )


def error_response(
    *,
    request: RpcRequest,
    code: str,
    message: str,
    retryable: bool = False,
) -> RpcResponse:
    return RpcResponse(
        request_id=request.request_id,
        session_id=request.session_id,
        ok=False,
        error=RpcError(code=code, message=message, retryable=retryable),
    )

