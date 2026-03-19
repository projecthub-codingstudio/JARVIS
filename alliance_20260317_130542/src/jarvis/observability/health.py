"""Health checks for JARVIS observability.

Checks: database, metrics, watched_folders, export_dir, model, embeddings,
vector_db, file_watcher, governor_state.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

# Maps health check keys to their dependency dict keys
_RUNTIME_DEP_MAP: dict[str, str] = {
    "model": "llm_generator",
    "embeddings": "embedding_runtime",
    "vector_db": "vector_index",
    "file_watcher": "file_watcher",
    "governor": "governor",
}

_CORE_KEYS: frozenset[str] = frozenset({"database", "metrics", "watched_folders", "export_dir"})
_RUNTIME_KEYS: frozenset[str] = frozenset({"model", "embeddings", "vector_db", "file_watcher", "governor"})


@dataclass
class HealthStatus:
    """System health status."""

    healthy: bool
    checks: dict[str, bool]
    details: dict[str, str]
    message: str = ""
    failed_checks: list[str] = field(default_factory=list)


def _has_runtime_failure(*, checks: dict[str, bool], deps: dict[str, object]) -> bool:
    """Return True when a provided runtime dependency is unhealthy."""
    for key in _RUNTIME_KEYS:
        if key in checks and not checks[key] and deps.get(_RUNTIME_DEP_MAP.get(key, key)) is not None:
            return True
    return False


def _failed_check_names(*, checks: dict[str, bool], deps: dict[str, object]) -> list[str]:
    """List failed checks that should degrade overall health."""
    return [
        name for name, ok in checks.items()
        if not ok and (name in _CORE_KEYS or deps.get(_RUNTIME_DEP_MAP.get(name, name)) is not None)
    ]


def check_health(deps: dict[str, object]) -> HealthStatus:
    """Run health checks against the dependency container.

    Supported dependency keys:
      - db: SQLite connection
      - metrics: MetricsCollector instance
      - config: JarvisConfig with watched_folders / export_dir
      - llm_generator: LLM runtime (has .model_id)
      - embedding_runtime: EmbeddingRuntime (has .model_loaded)
      - vector_index: VectorIndex (has ._table or similar)
      - file_watcher: FileWatcher (has .is_alive())
      - governor: Governor (has .sample())
    """
    checks: dict[str, bool] = {}
    details: dict[str, str] = {}

    # --- Core checks ---

    # Database
    db = deps.get("db")
    if db is not None:
        try:
            db.execute("SELECT 1")  # type: ignore[union-attr]
            checks["database"] = True
            details["database"] = "OK"
        except Exception:
            checks["database"] = False
            details["database"] = "query failed"
    else:
        checks["database"] = False
        details["database"] = "missing dependency"

    # Metrics
    checks["metrics"] = deps.get("metrics") is not None
    details["metrics"] = "OK" if checks["metrics"] else "missing dependency"

    # Watched folders
    config = deps.get("config")
    watched_folders = getattr(config, "watched_folders", None)
    if isinstance(watched_folders, list) and watched_folders:
        missing = [str(folder) for folder in watched_folders if not Path(folder).exists()]
        checks["watched_folders"] = not missing
        details["watched_folders"] = "OK" if not missing else f"missing: {', '.join(missing)}"
    else:
        checks["watched_folders"] = False
        details["watched_folders"] = "no folders configured"

    # Export dir
    export_dir = getattr(config, "export_dir", None)
    if export_dir is not None:
        export_path = Path(export_dir)
        ancestor = export_path
        while not ancestor.exists() and ancestor != ancestor.parent:
            ancestor = ancestor.parent
        parent_ok = ancestor.exists()
        checks["export_dir"] = parent_ok
        details["export_dir"] = "OK" if parent_ok else f"parent missing: {export_path.parent}"
    else:
        checks["export_dir"] = False
        details["export_dir"] = "not configured"

    # --- Runtime checks ---

    # LLM model
    llm = deps.get("llm_generator")
    if llm is not None:
        model_id = getattr(llm, "model_id", None)
        if model_id and model_id != "stub":
            checks["model"] = True
            details["model"] = f"OK ({model_id})"
        else:
            checks["model"] = False
            details["model"] = getattr(llm, "status_detail", "stub — no LLM loaded")
    else:
        checks["model"] = False
        details["model"] = "not configured"

    # Embedding runtime
    emb = deps.get("embedding_runtime")
    if emb is not None:
        model_loaded = getattr(emb, "model_loaded", None)
        if model_loaded is not None:
            checks["embeddings"] = bool(model_loaded)
            details["embeddings"] = "OK" if model_loaded else "model not loaded"
        else:
            # Fallback: check if the runtime object exists
            checks["embeddings"] = True
            details["embeddings"] = "OK (runtime present)"
    else:
        checks["embeddings"] = False
        details["embeddings"] = "not configured"

    # Vector DB (LanceDB)
    vi = deps.get("vector_index")
    if vi is not None:
        get_table = getattr(vi, "_get_table", None)
        if callable(get_table):
            table = get_table()
            checks["vector_db"] = table is not None
            details["vector_db"] = "OK" if table is not None else "table not initialized"
        else:
            table = getattr(vi, "_table", None)
            checks["vector_db"] = table is not None
            details["vector_db"] = "OK" if table is not None else "table not initialized"
    else:
        checks["vector_db"] = False
        details["vector_db"] = "not configured"

    # File watcher
    watcher = deps.get("file_watcher")
    if watcher is not None:
        is_alive = getattr(watcher, "is_alive", None)
        if callable(is_alive):
            alive = is_alive()
            checks["file_watcher"] = alive
            details["file_watcher"] = "OK" if alive else "watcher thread stopped"
        else:
            checks["file_watcher"] = True
            details["file_watcher"] = "OK (observer present)"
    else:
        checks["file_watcher"] = False
        details["file_watcher"] = "not running"

    # Governor state
    gov = deps.get("governor")
    if gov is not None:
        try:
            sample_fn = getattr(gov, "sample", None)
            if callable(sample_fn):
                state = sample_fn()
                thermal = getattr(state, "thermal_state", "unknown")
                mem_pct = getattr(state, "memory_pressure_pct", 0)
                swap_mb = getattr(state, "swap_used_mb", 0)
                on_ac = getattr(state, "on_ac_power", True)
                battery = getattr(state, "battery_pct", 100)

                gov_ok = thermal in ("nominal", "fair") and mem_pct < 80 and swap_mb < 2048
                checks["governor"] = gov_ok
                detail_parts = [f"thermal={thermal}", f"mem={mem_pct:.0f}%", f"swap={swap_mb}MB"]
                if not on_ac:
                    detail_parts.append(f"battery={battery}%")
                details["governor"] = ("OK" if gov_ok else "WARN") + f" ({', '.join(detail_parts)})"
            else:
                mode = getattr(gov, "mode", None)
                if mode is not None:
                    checks["governor"] = str(mode) == "GovernorMode.NORMAL"
                    details["governor"] = f"mode={mode}"
                else:
                    checks["governor"] = True
                    details["governor"] = "OK (stub)"
        except Exception as exc:
            checks["governor"] = False
            details["governor"] = f"sample failed: {exc}"
    else:
        checks["governor"] = True  # No governor = no constraints
        details["governor"] = "not configured (unconstrained)"

    # --- Aggregate ---
    # Core checks determine overall health.
    # Runtime checks are informational: "not configured" is OK (optional),
    # but "failed" or "stopped" means degraded.
    core_healthy = all(checks.get(k, False) for k in _CORE_KEYS if k in checks)
    runtime_healthy = not _has_runtime_failure(checks=checks, deps=deps)
    healthy = core_healthy and runtime_healthy
    failed = _failed_check_names(checks=checks, deps=deps)
    return HealthStatus(
        healthy=healthy,
        checks=checks,
        details=details,
        message="OK" if healthy else f"Degraded: {', '.join(failed)}",
        failed_checks=failed,
    )
