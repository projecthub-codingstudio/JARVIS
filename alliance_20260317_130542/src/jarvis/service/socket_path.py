"""Socket path helpers for the JARVIS local service."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

_DEFAULT_SOCKET_NAME = "jarvis_service.sock"


def resolve_socket_path() -> Path:
    override = os.getenv("JARVIS_SERVICE_SOCKET", "").strip()
    if override:
        return Path(override).expanduser().resolve()
    return (Path(tempfile.gettempdir()) / _DEFAULT_SOCKET_NAME).resolve()
