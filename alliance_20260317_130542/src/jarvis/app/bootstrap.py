"""Application bootstrap — builds the dependency graph and initializes JARVIS."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import NamedTuple

from jarvis.app.config import JarvisConfig
from jarvis.observability.metrics import MetricsCollector


class BootstrapResult(NamedTuple):
    """Typed container for bootstrap dependencies."""

    config: JarvisConfig
    db: sqlite3.Connection
    metrics: MetricsCollector


def init_database(config: JarvisConfig) -> sqlite3.Connection:
    """Initialize the SQLite database with the schema."""
    assert config.db_path is not None
    config.db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(config.db_path), check_same_thread=False)
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA foreign_keys = ON")

    schema_path = Path(__file__).parent.parent.parent.parent / "sql" / "schema.sql"
    if schema_path.exists():
        conn.executescript(schema_path.read_text())

    # Migration: add embedding_ref column if missing (added in v0.2)
    try:
        conn.execute("SELECT embedding_ref FROM chunks LIMIT 0")
    except sqlite3.OperationalError:
        conn.execute("ALTER TABLE chunks ADD COLUMN embedding_ref TEXT DEFAULT NULL")

    return conn


def create_metrics() -> MetricsCollector:
    """Create the global metrics collector."""
    return MetricsCollector()


def bootstrap(config: JarvisConfig | None = None) -> BootstrapResult:
    """Bootstrap the JARVIS application.

    Returns a typed BootstrapResult container. Phase 0 returns minimal stubs.
    Phase 1+ replaces stubs with real implementations.
    """
    if config is None:
        config = JarvisConfig()

    conn = init_database(config)
    metrics = create_metrics()

    return BootstrapResult(config=config, db=conn, metrics=metrics)
