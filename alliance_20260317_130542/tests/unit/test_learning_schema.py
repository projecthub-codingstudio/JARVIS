from __future__ import annotations

import sqlite3
from pathlib import Path


def test_schema_creates_required_tables(tmp_path: Path) -> None:
    from jarvis.learning import schema_sql_path

    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_path))
    sql = Path(schema_sql_path()).read_text(encoding="utf-8")
    conn.executescript(sql)

    tables = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()}
    assert "session_events" in tables
    assert "learned_patterns" in tables

    # session_events columns
    cols = {r[1] for r in conn.execute("PRAGMA table_info(session_events)").fetchall()}
    assert {"event_id", "session_id", "query_text", "outcome", "analyzed_at"} <= cols

    # learned_patterns columns
    cols = {r[1] for r in conn.execute("PRAGMA table_info(learned_patterns)").fetchall()}
    assert {"pattern_id", "canonical_query", "reformulation_type", "success_count"} <= cols
