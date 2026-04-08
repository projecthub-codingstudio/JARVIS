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
    """Resolve the data directory for the active profile.

    Priority:
      1. JARVIS_MENUBAR_DATA_DIR env var (explicit override)
      2. Active profile's data directory from profiles.json
      3. Legacy fallback: alliance_root / .jarvis-menubar
    """
    configured = os.getenv("JARVIS_MENUBAR_DATA_DIR", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()

    try:
        from jarvis.app.profile_manager import resolve_active_data_dir
        return resolve_active_data_dir()
    except Exception:
        return resolve_alliance_root(default_cwd) / ".jarvis-menubar"
