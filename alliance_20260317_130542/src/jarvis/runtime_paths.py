"""Shared path resolution helpers for menu bar runtime data."""

from __future__ import annotations

import os
from pathlib import Path


def resolve_alliance_root(default_cwd: Path | None = None) -> Path:
    configured = os.getenv("JARVIS_ALLIANCE_ROOT", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    return (default_cwd or Path.cwd()).expanduser().resolve()


def resolve_menubar_data_dir(default_cwd: Path | None = None) -> Path:
    configured = os.getenv("JARVIS_MENUBAR_DATA_DIR", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    return resolve_alliance_root(default_cwd) / ".jarvis-menubar"
