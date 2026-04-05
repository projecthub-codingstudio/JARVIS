-- src/jarvis/learning/schema.sql
CREATE TABLE IF NOT EXISTS session_events (
    event_id        TEXT PRIMARY KEY,
    session_id      TEXT NOT NULL,
    turn_id         TEXT NOT NULL,
    query_text      TEXT NOT NULL,
    retrieval_task  TEXT,
    entities_json   TEXT,
    outcome         TEXT NOT NULL,
    reason_code     TEXT,
    citation_paths  TEXT,
    confidence      REAL,
    created_at      INTEGER NOT NULL,
    analyzed_at     INTEGER
);
CREATE INDEX IF NOT EXISTS idx_session_events_session ON session_events(session_id, created_at);
CREATE INDEX IF NOT EXISTS idx_session_events_analyzed ON session_events(analyzed_at, created_at);

CREATE TABLE IF NOT EXISTS learned_patterns (
    pattern_id          TEXT PRIMARY KEY,
    canonical_query     TEXT NOT NULL,
    failed_variants     TEXT,
    retrieval_task      TEXT NOT NULL,
    entity_hints_json   TEXT NOT NULL,
    reformulation_type  TEXT NOT NULL,
    success_count       INTEGER DEFAULT 1,
    citation_paths      TEXT,
    created_at          INTEGER NOT NULL,
    last_used_at        INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_patterns_task ON learned_patterns(retrieval_task);
CREATE INDEX IF NOT EXISTS idx_patterns_last_used ON learned_patterns(last_used_at);
