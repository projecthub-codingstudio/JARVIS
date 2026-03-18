-- JARVIS MVP Schema
-- 5 required tables + FTS5 virtual table
-- SQLite 3.35+ required for FTS5 support

PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

-- ============================================================
-- documents: indexed file metadata
-- ============================================================
CREATE TABLE IF NOT EXISTS documents (
    document_id   TEXT PRIMARY KEY,
    path          TEXT NOT NULL UNIQUE,
    content_hash  TEXT NOT NULL DEFAULT '',
    size_bytes    INTEGER NOT NULL DEFAULT 0,
    modified_at   TEXT NOT NULL DEFAULT (datetime('now')),
    indexing_status TEXT NOT NULL DEFAULT 'PENDING'
        CHECK (indexing_status IN ('PENDING', 'INDEXING', 'INDEXED', 'FAILED', 'TOMBSTONED')),
    access_status TEXT NOT NULL DEFAULT 'ACCESSIBLE'
        CHECK (access_status IN ('ACCESSIBLE', 'DENIED', 'NOT_FOUND')),
    created_at    TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_documents_path ON documents(path);
CREATE INDEX IF NOT EXISTS idx_documents_status ON documents(indexing_status);

-- ============================================================
-- chunks: document segments for retrieval
-- ============================================================
CREATE TABLE IF NOT EXISTS chunks (
    chunk_id      TEXT PRIMARY KEY,
    document_id   TEXT NOT NULL REFERENCES documents(document_id) ON DELETE CASCADE,
    byte_start    INTEGER NOT NULL DEFAULT 0,
    byte_end      INTEGER NOT NULL DEFAULT 0,
    line_start    INTEGER NOT NULL DEFAULT 0,
    line_end      INTEGER NOT NULL DEFAULT 0,
    text          TEXT NOT NULL DEFAULT '',
    chunk_hash    TEXT NOT NULL DEFAULT '',
    lexical_morphs TEXT NOT NULL DEFAULT '',
    heading_path  TEXT NOT NULL DEFAULT '',
    embedding_ref TEXT DEFAULT NULL,
    created_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_chunks_document ON chunks(document_id);

-- ============================================================
-- FTS5 virtual table for full-text search on chunk text
-- ============================================================
CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
    text,
    lexical_morphs,
    content='chunks',
    content_rowid='rowid'
);

-- Triggers to keep FTS5 index in sync with chunks table
-- Include lexical_morphs for Korean morpheme-expanded search
CREATE TRIGGER IF NOT EXISTS chunks_ai AFTER INSERT ON chunks BEGIN
    INSERT INTO chunks_fts(rowid, text, lexical_morphs) VALUES (new.rowid, new.text, new.lexical_morphs);
END;

CREATE TRIGGER IF NOT EXISTS chunks_ad AFTER DELETE ON chunks BEGIN
    INSERT INTO chunks_fts(chunks_fts, rowid, text, lexical_morphs) VALUES ('delete', old.rowid, old.text, old.lexical_morphs);
END;

CREATE TRIGGER IF NOT EXISTS chunks_au AFTER UPDATE ON chunks BEGIN
    INSERT INTO chunks_fts(chunks_fts, rowid, text, lexical_morphs) VALUES ('delete', old.rowid, old.text, old.lexical_morphs);
    INSERT INTO chunks_fts(rowid, text, lexical_morphs) VALUES (new.rowid, new.text, new.lexical_morphs);
END;

-- ============================================================
-- citations: links between evidence items and source chunks
-- ============================================================
CREATE TABLE IF NOT EXISTS citations (
    citation_id     TEXT PRIMARY KEY,
    document_id     TEXT NOT NULL REFERENCES documents(document_id) ON DELETE CASCADE,
    chunk_id        TEXT NOT NULL REFERENCES chunks(chunk_id) ON DELETE CASCADE,
    label           TEXT NOT NULL DEFAULT '',
    state           TEXT NOT NULL DEFAULT 'VALID'
        CHECK (state IN ('VALID', 'STALE', 'REINDEXING', 'MISSING', 'ACCESS_LOST')),
    last_verified   TEXT NOT NULL DEFAULT (datetime('now')),
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_citations_document ON citations(document_id);
CREATE INDEX IF NOT EXISTS idx_citations_chunk ON citations(chunk_id);
CREATE INDEX IF NOT EXISTS idx_citations_state ON citations(state);

-- ============================================================
-- conversation_turns: conversation history
-- ============================================================
CREATE TABLE IF NOT EXISTS conversation_turns (
    turn_id          TEXT PRIMARY KEY,
    user_input       TEXT NOT NULL DEFAULT '',
    assistant_output TEXT NOT NULL DEFAULT '',
    has_evidence     INTEGER NOT NULL DEFAULT 0,
    created_at       TEXT NOT NULL DEFAULT (datetime('now')),
    completed_at     TEXT
);

-- ============================================================
-- task_logs: observability and audit trail
-- ============================================================
CREATE TABLE IF NOT EXISTS task_logs (
    entry_id     TEXT PRIMARY KEY,
    turn_id      TEXT NOT NULL DEFAULT '',
    stage        TEXT NOT NULL DEFAULT '',
    status       TEXT NOT NULL DEFAULT 'PENDING'
        CHECK (status IN ('PENDING', 'RUNNING', 'COMPLETED', 'FAILED', 'SKIPPED')),
    error_code   TEXT NOT NULL DEFAULT '',
    duration_ms  REAL NOT NULL DEFAULT 0.0,
    metadata     TEXT NOT NULL DEFAULT '{}',
    created_at   TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_task_logs_turn ON task_logs(turn_id);
CREATE INDEX IF NOT EXISTS idx_task_logs_stage ON task_logs(stage);
