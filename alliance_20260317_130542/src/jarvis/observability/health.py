"""Health check stubs for JARVIS observability. Phase 0: basic checks."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class HealthStatus:
    """System health status."""

    healthy: bool
    checks: dict[str, bool]
    details: dict[str, str]
    message: str = ""


def check_health(deps: dict[str, object]) -> HealthStatus:
    """Run basic health checks against the dependency container."""
    checks: dict[str, bool] = {}
    details: dict[str, str] = {}

    # Check database
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

    # Check metrics
    checks["metrics"] = deps.get("metrics") is not None
    details["metrics"] = "OK" if checks["metrics"] else "missing dependency"

    config = deps.get("config")
    watched_folders = getattr(config, "watched_folders", None)
    if isinstance(watched_folders, list) and watched_folders:
        missing = [str(folder) for folder in watched_folders if not Path(folder).exists()]
        checks["watched_folders"] = not missing
        details["watched_folders"] = "OK" if not missing else f"missing: {', '.join(missing)}"
    else:
        checks["watched_folders"] = False
        details["watched_folders"] = "no folders configured"

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

    healthy = all(checks.values())
    failed = [name for name, ok in checks.items() if not ok]
    return HealthStatus(
        healthy=healthy,
        checks=checks,
        details=details,
        message="OK" if healthy else f"Degraded: {', '.join(failed)}",
    )
