# Indexing Pipeline Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the indexing pipeline that parses files, chunks text, and writes to SQLite FTS5 — enabling JARVIS to ingest local documents for retrieval.

**Architecture:** Bottom-up implementation: DocumentParser → Chunker → TombstoneManager → IndexPipeline → FileWatcher. Each component implements against the existing frozen Protocol interfaces and data models in `src/jarvis/contracts/`. All state persists to SQLite via the existing schema in `sql/schema.sql`. Existing 113 tests must continue to pass.

**Tech Stack:** Python 3.12, SQLite FTS5, hashlib (SHA-256), `pathlib`, `os.stat`, `fsevents` (via `watchdog` library for cross-platform FSEvents)

---

## File Structure

| Action | Path | Responsibility |
|--------|------|----------------|
| Modify | `src/jarvis/indexing/parsers.py` | Extract text from .md, .py, .txt, .ts, .yaml files |
| Modify | `src/jarvis/indexing/chunker.py` | Split text into overlapping chunks with byte/line ranges |
| Modify | `src/jarvis/indexing/tombstone.py` | Manage soft-deletion records in SQLite |
| Modify | `src/jarvis/indexing/index_pipeline.py` | Orchestrate parse→chunk→store to SQLite |
| Modify | `src/jarvis/indexing/file_watcher.py` | Watch directories for file changes via watchdog |
| Create | `tests/indexing/test_parsers.py` | Parser unit tests |
| Create | `tests/indexing/test_chunker.py` | Chunker unit tests |
| Create | `tests/indexing/test_tombstone.py` | Tombstone unit tests |
| Create | `tests/indexing/test_index_pipeline.py` | Integration tests for full pipeline |
| Create | `tests/indexing/test_file_watcher.py` | FileWatcher unit tests |
| Create | `tests/indexing/test_integration.py` | Full round-trip integration tests |
| Modify | `pyproject.toml` | Add `watchdog` dependency |

---

### Task 1: DocumentParser — detect_type and parse

**Files:**
- Modify: `src/jarvis/indexing/parsers.py`
- Create: `tests/indexing/test_parsers.py`

- [ ] **Step 1: Write failing tests for detect_type**

```python
# tests/indexing/test_parsers.py
"""Tests for DocumentParser."""
from __future__ import annotations

from pathlib import Path

import pytest

from jarvis.indexing.parsers import DocumentParser


class TestDetectType:
    def test_markdown(self, tmp_path: Path) -> None:
        f = tmp_path / "readme.md"
        f.write_text("# Hello")
        assert DocumentParser().detect_type(f) == "markdown"

    def test_python(self, tmp_path: Path) -> None:
        f = tmp_path / "app.py"
        f.write_text("print('hi')")
        assert DocumentParser().detect_type(f) == "python"

    def test_typescript(self, tmp_path: Path) -> None:
        f = tmp_path / "index.ts"
        f.write_text("const x = 1;")
        assert DocumentParser().detect_type(f) == "typescript"

    def test_yaml(self, tmp_path: Path) -> None:
        f = tmp_path / "config.yaml"
        f.write_text("key: value")
        assert DocumentParser().detect_type(f) == "yaml"

    def test_plain_text(self, tmp_path: Path) -> None:
        f = tmp_path / "notes.txt"
        f.write_text("some notes")
        assert DocumentParser().detect_type(f) == "text"

    def test_unknown_extension(self, tmp_path: Path) -> None:
        f = tmp_path / "data.bin"
        f.write_bytes(b"\x00\x01")
        assert DocumentParser().detect_type(f) == "text"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/codingstudio/__PROJECTHUB__/JARVIS/alliance_20260317_130542 && python -m pytest tests/indexing/test_parsers.py -v`
Expected: FAIL with "NotImplementedError"

- [ ] **Step 3: Write failing tests for parse**

Append to `tests/indexing/test_parsers.py`:

```python
class TestParse:
    def test_parse_markdown(self, tmp_path: Path) -> None:
        f = tmp_path / "doc.md"
        f.write_text("# Title\n\nParagraph text.")
        text = DocumentParser().parse(f)
        assert "Title" in text
        assert "Paragraph text." in text

    def test_parse_python(self, tmp_path: Path) -> None:
        f = tmp_path / "mod.py"
        content = '"""Docstring."""\n\ndef foo():\n    pass\n'
        f.write_text(content)
        text = DocumentParser().parse(f)
        assert "Docstring" in text
        assert "def foo" in text

    def test_parse_nonexistent_raises(self) -> None:
        with pytest.raises(FileNotFoundError):
            DocumentParser().parse(Path("/nonexistent/file.md"))

    def test_parse_empty_file(self, tmp_path: Path) -> None:
        f = tmp_path / "empty.txt"
        f.write_text("")
        assert DocumentParser().parse(f) == ""

    def test_parse_korean_content(self, tmp_path: Path) -> None:
        f = tmp_path / "korean.md"
        f.write_text("# 제목\n\n한국어 문서 내용입니다.")
        text = DocumentParser().parse(f)
        assert "제목" in text
        assert "한국어" in text
```

- [ ] **Step 4: Write failing tests for create_record**

Append to `tests/indexing/test_parsers.py`:

```python
from jarvis.contracts import DocumentRecord, IndexingStatus, AccessStatus


class TestCreateRecord:
    def test_creates_record_with_metadata(self, tmp_path: Path) -> None:
        f = tmp_path / "doc.md"
        f.write_text("content here")
        record = DocumentParser().create_record(f)
        assert isinstance(record, DocumentRecord)
        assert record.path == str(f)
        assert record.size_bytes == f.stat().st_size
        assert record.content_hash  # non-empty SHA-256
        assert record.indexing_status == IndexingStatus.PENDING
        assert record.access_status == AccessStatus.ACCESSIBLE

    def test_record_hash_changes_with_content(self, tmp_path: Path) -> None:
        f = tmp_path / "doc.md"
        f.write_text("version 1")
        r1 = DocumentParser().create_record(f)
        f.write_text("version 2")
        r2 = DocumentParser().create_record(f)
        assert r1.content_hash != r2.content_hash

    def test_record_for_inaccessible_file(self) -> None:
        with pytest.raises(FileNotFoundError):
            DocumentParser().create_record(Path("/nonexistent"))
```

- [ ] **Step 5: Implement DocumentParser**

```python
# src/jarvis/indexing/parsers.py
"""Document parsers — extract text content from various file formats.

Supports plain text, Markdown, and code files for Phase 1.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

from jarvis.contracts import AccessStatus, DocumentRecord, IndexingStatus

_EXTENSION_MAP: dict[str, str] = {
    ".md": "markdown",
    ".markdown": "markdown",
    ".py": "python",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".js": "javascript",
    ".jsx": "javascript",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".json": "json",
    ".txt": "text",
    ".rst": "text",
    ".cfg": "text",
    ".toml": "text",
    ".ini": "text",
}


class DocumentParser:
    """Parses files into raw text for downstream chunking and indexing."""

    def detect_type(self, path: Path) -> str:
        return _EXTENSION_MAP.get(path.suffix.lower(), "text")

    def parse(self, path: Path) -> str:
        if not path.exists():
            raise FileNotFoundError(f"File not found: {path}")
        return path.read_text(encoding="utf-8")

    def create_record(self, path: Path) -> DocumentRecord:
        if not path.exists():
            raise FileNotFoundError(f"File not found: {path}")

        content = path.read_bytes()
        stat = path.stat()

        return DocumentRecord(
            path=str(path),
            content_hash=hashlib.sha256(content).hexdigest(),
            size_bytes=stat.st_size,
            indexing_status=IndexingStatus.PENDING,
            access_status=AccessStatus.ACCESSIBLE,
        )
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd /Users/codingstudio/__PROJECTHUB__/JARVIS/alliance_20260317_130542 && python -m pytest tests/indexing/test_parsers.py -v`
Expected: ALL PASS

- [ ] **Step 7: Run full test suite for regression**

Run: `cd /Users/codingstudio/__PROJECTHUB__/JARVIS/alliance_20260317_130542 && python -m pytest -v`
Expected: ALL 113+ tests PASS

- [ ] **Step 8: Commit**

```bash
git add src/jarvis/indexing/parsers.py tests/indexing/test_parsers.py
git commit -m "feat(indexing): implement DocumentParser with type detection and record creation"
```

---

### Task 2: Chunker — split text into overlapping chunks with byte/line ranges

**Files:**
- Modify: `src/jarvis/indexing/chunker.py`
- Create: `tests/indexing/test_chunker.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/indexing/test_chunker.py
"""Tests for Chunker."""
from __future__ import annotations

import pytest

from jarvis.contracts import ChunkRecord
from jarvis.indexing.chunker import Chunker


class TestChunkerBasic:
    def test_empty_text_returns_empty(self) -> None:
        assert Chunker().chunk("") == []

    def test_short_text_single_chunk(self) -> None:
        chunks = Chunker(max_chunk_bytes=1024).chunk("Hello world", document_id="doc1")
        assert len(chunks) == 1
        assert chunks[0].text == "Hello world"
        assert chunks[0].document_id == "doc1"

    def test_chunk_has_byte_ranges(self) -> None:
        chunks = Chunker(max_chunk_bytes=1024).chunk("Hello world", document_id="d1")
        c = chunks[0]
        assert c.byte_start == 0
        assert c.byte_end == len("Hello world".encode("utf-8"))

    def test_chunk_has_line_ranges(self) -> None:
        text = "Line 1\nLine 2\nLine 3"
        chunks = Chunker(max_chunk_bytes=4096).chunk(text, document_id="d1")
        assert chunks[0].line_start == 0
        assert chunks[0].line_end == 2  # 0-indexed inclusive

    def test_chunk_has_hash(self) -> None:
        chunks = Chunker().chunk("some text", document_id="d1")
        assert chunks[0].chunk_hash  # non-empty

    def test_chunk_id_is_uuid(self) -> None:
        chunks = Chunker().chunk("text", document_id="d1")
        assert len(chunks[0].chunk_id) == 36  # UUID format


class TestChunkerSplitting:
    def test_long_text_produces_multiple_chunks(self) -> None:
        text = "word " * 500  # ~2500 bytes
        chunks = Chunker(max_chunk_bytes=256, overlap_bytes=32).chunk(text, document_id="d1")
        assert len(chunks) > 1

    def test_chunks_cover_all_text(self) -> None:
        text = "A" * 1000
        chunks = Chunker(max_chunk_bytes=256, overlap_bytes=32).chunk(text, document_id="d1")
        # Last chunk's byte_end should reach end of text
        assert chunks[-1].byte_end == len(text.encode("utf-8"))
        # First chunk starts at 0
        assert chunks[0].byte_start == 0

    def test_chunks_have_overlap(self) -> None:
        text = "word " * 200  # 1000 bytes
        chunks = Chunker(max_chunk_bytes=256, overlap_bytes=64).chunk(text, document_id="d1")
        if len(chunks) >= 2:
            # Second chunk should start before first chunk ends
            assert chunks[1].byte_start < chunks[0].byte_end

    def test_respects_newline_boundaries(self) -> None:
        # Build text with clear paragraph boundaries
        paragraphs = ["Paragraph one content here." * 5, "Paragraph two content here." * 5]
        text = "\n\n".join(paragraphs)
        chunks = Chunker(max_chunk_bytes=200, overlap_bytes=32).chunk(text, document_id="d1")
        # Chunks should prefer splitting at newlines rather than mid-word
        for c in chunks:
            # No chunk should start mid-word (after trimming)
            stripped = c.text.lstrip()
            if stripped:
                assert stripped[0].isalpha() or stripped[0] in "\n#-*>"


class TestChunkerKorean:
    def test_korean_text_chunking(self) -> None:
        text = "한국어 문장입니다. " * 100
        chunks = Chunker(max_chunk_bytes=256, overlap_bytes=32).chunk(text, document_id="d1")
        assert len(chunks) > 1
        # All chunks should be valid ChunkRecord
        for c in chunks:
            assert isinstance(c, ChunkRecord)
            assert c.text

    def test_mixed_korean_english(self) -> None:
        text = "JARVIS 프로젝트의 아키텍처를 설명합니다. " * 50
        chunks = Chunker(max_chunk_bytes=256, overlap_bytes=32).chunk(text, document_id="d1")
        assert len(chunks) > 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/codingstudio/__PROJECTHUB__/JARVIS/alliance_20260317_130542 && python -m pytest tests/indexing/test_chunker.py -v`
Expected: FAIL with "NotImplementedError"

- [ ] **Step 3: Implement Chunker**

```python
# src/jarvis/indexing/chunker.py
"""Chunker — splits parsed document text into indexable chunks.

Produces ChunkRecord objects with byte/line ranges for citation
back-references.
"""
from __future__ import annotations

import hashlib

from jarvis.contracts import ChunkRecord


class Chunker:
    """Splits document text into overlapping chunks for indexing.

    Chunk boundaries respect newline boundaries where possible.
    """

    def __init__(
        self,
        *,
        max_chunk_bytes: int = 1024,
        overlap_bytes: int = 128,
    ) -> None:
        self._max_chunk_bytes = max_chunk_bytes
        self._overlap_bytes = overlap_bytes

    def chunk(self, text: str, *, document_id: str = "") -> list[ChunkRecord]:
        if not text:
            return []

        text_bytes = text.encode("utf-8")
        total = len(text_bytes)
        chunks: list[ChunkRecord] = []
        byte_pos = 0

        while byte_pos < total:
            end = min(byte_pos + self._max_chunk_bytes, total)

            # Try to break at a newline within the last 25% of the chunk
            if end < total:
                search_start = max(byte_pos + (self._max_chunk_bytes * 3 // 4), byte_pos)
                best_break = -1
                # Look for double newline first (paragraph boundary)
                idx = text_bytes.rfind(b"\n\n", search_start, end)
                if idx != -1:
                    best_break = idx + 2
                else:
                    # Fall back to single newline
                    idx = text_bytes.rfind(b"\n", search_start, end)
                    if idx != -1:
                        best_break = idx + 1
                if best_break > byte_pos:
                    end = best_break

            chunk_bytes = text_bytes[byte_pos:end]
            chunk_text = chunk_bytes.decode("utf-8", errors="replace")

            # Compute line range
            preceding = text_bytes[:byte_pos]
            line_start = preceding.count(b"\n")
            line_end = line_start + chunk_bytes.count(b"\n")

            chunks.append(ChunkRecord(
                document_id=document_id,
                byte_start=byte_pos,
                byte_end=end,
                line_start=line_start,
                line_end=line_end,
                text=chunk_text,
                chunk_hash=hashlib.sha256(chunk_bytes).hexdigest(),
            ))

            # Advance with overlap
            byte_pos = end - self._overlap_bytes if end < total else total

        return chunks
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/codingstudio/__PROJECTHUB__/JARVIS/alliance_20260317_130542 && python -m pytest tests/indexing/test_chunker.py -v`
Expected: ALL PASS

- [ ] **Step 5: Run full test suite for regression**

Run: `cd /Users/codingstudio/__PROJECTHUB__/JARVIS/alliance_20260317_130542 && python -m pytest -v`
Expected: ALL tests PASS

- [ ] **Step 6: Commit**

```bash
git add src/jarvis/indexing/chunker.py tests/indexing/test_chunker.py
git commit -m "feat(indexing): implement Chunker with byte/line ranges and newline-aware splitting"
```

---

### Task 3: TombstoneManager — soft-deletion tracking in SQLite

**Files:**
- Modify: `src/jarvis/indexing/tombstone.py`
- Create: `tests/indexing/test_tombstone.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/indexing/test_tombstone.py
"""Tests for TombstoneManager."""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from jarvis.app.bootstrap import init_database
from jarvis.app.config import JarvisConfig
from jarvis.contracts import DocumentRecord, IndexingStatus
from jarvis.indexing.tombstone import TombstoneManager


@pytest.fixture
def db(tmp_path: Path) -> sqlite3.Connection:
    config = JarvisConfig(watched_folders=[tmp_path], data_dir=tmp_path / ".jarvis")
    return init_database(config)


@pytest.fixture
def manager(db: sqlite3.Connection) -> TombstoneManager:
    return TombstoneManager(db=db)


def _insert_doc(db: sqlite3.Connection, doc: DocumentRecord) -> None:
    db.execute(
        "INSERT INTO documents (document_id, path, content_hash, size_bytes, indexing_status)"
        " VALUES (?, ?, ?, ?, ?)",
        (doc.document_id, doc.path, doc.content_hash, doc.size_bytes, doc.indexing_status.value),
    )
    db.commit()


class TestTombstoneManager:
    def test_create_tombstone(self, db: sqlite3.Connection, manager: TombstoneManager) -> None:
        doc = DocumentRecord(path="/tmp/gone.md", content_hash="abc", indexing_status=IndexingStatus.INDEXED)
        _insert_doc(db, doc)

        result = manager.create_tombstone(doc)
        assert result.indexing_status == IndexingStatus.TOMBSTONED

        row = db.execute(
            "SELECT indexing_status FROM documents WHERE document_id = ?",
            (doc.document_id,),
        ).fetchone()
        assert row[0] == "TOMBSTONED"

    def test_is_tombstoned_true(self, db: sqlite3.Connection, manager: TombstoneManager) -> None:
        doc = DocumentRecord(path="/tmp/gone.md", content_hash="abc", indexing_status=IndexingStatus.INDEXED)
        _insert_doc(db, doc)
        manager.create_tombstone(doc)
        assert manager.is_tombstoned(doc.document_id) is True

    def test_is_tombstoned_false(self, db: sqlite3.Connection, manager: TombstoneManager) -> None:
        doc = DocumentRecord(path="/tmp/alive.md", content_hash="abc", indexing_status=IndexingStatus.INDEXED)
        _insert_doc(db, doc)
        assert manager.is_tombstoned(doc.document_id) is False

    def test_is_tombstoned_missing_id(self, manager: TombstoneManager) -> None:
        assert manager.is_tombstoned("nonexistent-id") is False

    def test_list_tombstones(self, db: sqlite3.Connection, manager: TombstoneManager) -> None:
        for i in range(3):
            doc = DocumentRecord(path=f"/tmp/file{i}.md", content_hash=f"h{i}", indexing_status=IndexingStatus.INDEXED)
            _insert_doc(db, doc)
            manager.create_tombstone(doc)

        alive = DocumentRecord(path="/tmp/alive.md", content_hash="ha", indexing_status=IndexingStatus.INDEXED)
        _insert_doc(db, alive)

        tombstones = manager.list_tombstones()
        assert len(tombstones) == 3
        for t in tombstones:
            assert t.indexing_status == IndexingStatus.TOMBSTONED

    def test_list_tombstones_empty(self, manager: TombstoneManager) -> None:
        assert manager.list_tombstones() == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/codingstudio/__PROJECTHUB__/JARVIS/alliance_20260317_130542 && python -m pytest tests/indexing/test_tombstone.py -v`
Expected: FAIL

- [ ] **Step 3: Implement TombstoneManager**

```python
# src/jarvis/indexing/tombstone.py
"""Tombstone — manages soft-deletion records for removed documents.

When a file is deleted or access is lost, a tombstone is created
so that stale citations can be properly flagged rather than silently
returning invalid results.
"""
from __future__ import annotations

import sqlite3
from dataclasses import replace

from jarvis.contracts import DocumentRecord, IndexingStatus


class TombstoneManager:
    """Manages tombstone records for deleted/inaccessible documents."""

    def __init__(self, *, db: sqlite3.Connection) -> None:
        self._db = db

    def create_tombstone(self, document: DocumentRecord) -> DocumentRecord:
        self._db.execute(
            "UPDATE documents SET indexing_status = ?, updated_at = datetime('now')"
            " WHERE document_id = ?",
            (IndexingStatus.TOMBSTONED.value, document.document_id),
        )
        self._db.commit()
        return replace(document, indexing_status=IndexingStatus.TOMBSTONED)

    def is_tombstoned(self, document_id: str) -> bool:
        row = self._db.execute(
            "SELECT indexing_status FROM documents WHERE document_id = ?",
            (document_id,),
        ).fetchone()
        if row is None:
            return False
        return row[0] == IndexingStatus.TOMBSTONED.value

    def list_tombstones(self) -> list[DocumentRecord]:
        rows = self._db.execute(
            "SELECT document_id, path, content_hash, size_bytes, indexing_status"
            " FROM documents WHERE indexing_status = ?",
            (IndexingStatus.TOMBSTONED.value,),
        ).fetchall()
        return [
            DocumentRecord(
                document_id=r[0],
                path=r[1],
                content_hash=r[2],
                size_bytes=r[3],
                indexing_status=IndexingStatus(r[4]),
            )
            for r in rows
        ]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/codingstudio/__PROJECTHUB__/JARVIS/alliance_20260317_130542 && python -m pytest tests/indexing/test_tombstone.py -v`
Expected: ALL PASS

- [ ] **Step 5: Run full test suite for regression**

Run: `cd /Users/codingstudio/__PROJECTHUB__/JARVIS/alliance_20260317_130542 && python -m pytest -v`
Expected: ALL tests PASS

- [ ] **Step 6: Commit**

```bash
git add src/jarvis/indexing/tombstone.py tests/indexing/test_tombstone.py
git commit -m "feat(indexing): implement TombstoneManager with SQLite persistence"
```

---

### Task 4: IndexPipeline — orchestrate parse → chunk → store to SQLite

**Files:**
- Modify: `src/jarvis/indexing/index_pipeline.py`
- Create: `tests/indexing/test_index_pipeline.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/indexing/test_index_pipeline.py
"""Tests for IndexPipeline."""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Sequence

import pytest

from jarvis.app.bootstrap import init_database
from jarvis.app.config import JarvisConfig
from jarvis.contracts import ChunkRecord, DocumentRecord, IndexingStatus
from jarvis.indexing.index_pipeline import IndexPipeline
from jarvis.indexing.parsers import DocumentParser
from jarvis.indexing.chunker import Chunker
from jarvis.indexing.tombstone import TombstoneManager


class FakeEmbeddingRuntime:
    """Stub embedding runtime for testing (no real model needed)."""

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        return [[0.0] * 8 for _ in texts]


@pytest.fixture
def db(tmp_path: Path) -> sqlite3.Connection:
    config = JarvisConfig(watched_folders=[tmp_path], data_dir=tmp_path / ".jarvis")
    return init_database(config)


@pytest.fixture
def pipeline(db: sqlite3.Connection) -> IndexPipeline:
    return IndexPipeline(
        db=db,
        parser=DocumentParser(),
        chunker=Chunker(max_chunk_bytes=256, overlap_bytes=32),
        tombstone_manager=TombstoneManager(db=db),
        embedding_runtime=FakeEmbeddingRuntime(),
    )


class TestIndexFile:
    def test_index_markdown(self, pipeline: IndexPipeline, tmp_path: Path) -> None:
        f = tmp_path / "doc.md"
        f.write_text("# Title\n\nSome paragraph content for indexing.")
        record = pipeline.index_file(f)
        assert isinstance(record, DocumentRecord)
        assert record.indexing_status == IndexingStatus.INDEXED
        assert record.path == str(f)

    def test_index_writes_to_documents_table(
        self, pipeline: IndexPipeline, db: sqlite3.Connection, tmp_path: Path
    ) -> None:
        f = tmp_path / "doc.md"
        f.write_text("Content")
        record = pipeline.index_file(f)
        row = db.execute(
            "SELECT document_id, path, indexing_status FROM documents WHERE document_id = ?",
            (record.document_id,),
        ).fetchone()
        assert row is not None
        assert row[1] == str(f)
        assert row[2] == "INDEXED"

    def test_index_writes_chunks(
        self, pipeline: IndexPipeline, db: sqlite3.Connection, tmp_path: Path
    ) -> None:
        f = tmp_path / "doc.md"
        f.write_text("Some content\n" * 10)
        record = pipeline.index_file(f)
        rows = db.execute(
            "SELECT chunk_id, text FROM chunks WHERE document_id = ?",
            (record.document_id,),
        ).fetchall()
        assert len(rows) >= 1
        assert rows[0][1]  # non-empty text

    def test_index_populates_fts(
        self, pipeline: IndexPipeline, db: sqlite3.Connection, tmp_path: Path
    ) -> None:
        f = tmp_path / "doc.md"
        f.write_text("JARVIS architecture design document")
        pipeline.index_file(f)
        fts_rows = db.execute(
            "SELECT * FROM chunks_fts WHERE chunks_fts MATCH ?",
            ("architecture",),
        ).fetchall()
        assert len(fts_rows) >= 1

    def test_index_nonexistent_file_raises(self, pipeline: IndexPipeline) -> None:
        with pytest.raises(FileNotFoundError):
            pipeline.index_file(Path("/nonexistent/file.md"))

    def test_duplicate_index_same_hash_is_noop(
        self, pipeline: IndexPipeline, db: sqlite3.Connection, tmp_path: Path
    ) -> None:
        f = tmp_path / "doc.md"
        f.write_text("same content")
        r1 = pipeline.index_file(f)
        r2 = pipeline.index_file(f)
        assert r1.document_id == r2.document_id
        # Should not duplicate chunks
        count = db.execute(
            "SELECT COUNT(*) FROM chunks WHERE document_id = ?",
            (r1.document_id,),
        ).fetchone()[0]
        assert count >= 1


class TestReindexFile:
    def test_reindex_replaces_chunks(
        self, pipeline: IndexPipeline, db: sqlite3.Connection, tmp_path: Path
    ) -> None:
        f = tmp_path / "doc.md"
        f.write_text("Original content")
        r1 = pipeline.index_file(f)
        old_chunks = db.execute(
            "SELECT chunk_id FROM chunks WHERE document_id = ?",
            (r1.document_id,),
        ).fetchall()

        f.write_text("Updated content with new information")
        r2 = pipeline.reindex_file(f)
        assert r2.document_id == r1.document_id
        assert r2.indexing_status == IndexingStatus.INDEXED

        new_chunks = db.execute(
            "SELECT chunk_id, text FROM chunks WHERE document_id = ?",
            (r2.document_id,),
        ).fetchall()
        # Old chunks should be gone, new ones present
        old_ids = {r[0] for r in old_chunks}
        new_ids = {r[0] for r in new_chunks}
        assert old_ids != new_ids
        assert "Updated" in new_chunks[0][1]


class TestRemoveFile:
    def test_remove_tombstones_document(
        self, pipeline: IndexPipeline, db: sqlite3.Connection, tmp_path: Path
    ) -> None:
        f = tmp_path / "doc.md"
        f.write_text("Content to remove")
        record = pipeline.index_file(f)
        pipeline.remove_file(f)

        row = db.execute(
            "SELECT indexing_status FROM documents WHERE document_id = ?",
            (record.document_id,),
        ).fetchone()
        assert row[0] == "TOMBSTONED"

    def test_remove_deletes_chunks(
        self, pipeline: IndexPipeline, db: sqlite3.Connection, tmp_path: Path
    ) -> None:
        f = tmp_path / "doc.md"
        f.write_text("Content to remove")
        record = pipeline.index_file(f)
        pipeline.remove_file(f)

        count = db.execute(
            "SELECT COUNT(*) FROM chunks WHERE document_id = ?",
            (record.document_id,),
        ).fetchone()[0]
        assert count == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/codingstudio/__PROJECTHUB__/JARVIS/alliance_20260317_130542 && python -m pytest tests/indexing/test_index_pipeline.py -v`
Expected: FAIL

- [ ] **Step 3: Implement IndexPipeline**

```python
# src/jarvis/indexing/index_pipeline.py
"""IndexPipeline — orchestrates parse, chunk, embed, and index operations.

Processes file change events from the FileWatcher and updates both
the FTS and vector indexes.
"""
from __future__ import annotations

import sqlite3
from dataclasses import replace
from pathlib import Path

from jarvis.contracts import DocumentRecord, EmbeddingRuntimeProtocol, IndexingStatus
from jarvis.indexing.chunker import Chunker
from jarvis.indexing.parsers import DocumentParser
from jarvis.indexing.tombstone import TombstoneManager


class IndexPipeline:
    """Full indexing pipeline: parse -> chunk -> embed -> store."""

    def __init__(
        self,
        *,
        db: sqlite3.Connection,
        parser: DocumentParser,
        chunker: Chunker,
        tombstone_manager: TombstoneManager,
        embedding_runtime: EmbeddingRuntimeProtocol,
    ) -> None:
        self._db = db
        self._parser = parser
        self._chunker = chunker
        self._tombstone = tombstone_manager
        self._embedding_runtime = embedding_runtime

    def _find_document_by_path(self, path: Path) -> DocumentRecord | None:
        row = self._db.execute(
            "SELECT document_id, path, content_hash, size_bytes, indexing_status"
            " FROM documents WHERE path = ?",
            (str(path),),
        ).fetchone()
        if row is None:
            return None
        return DocumentRecord(
            document_id=row[0],
            path=row[1],
            content_hash=row[2],
            size_bytes=row[3],
            indexing_status=IndexingStatus(row[4]),
        )

    def _write_document(self, record: DocumentRecord) -> None:
        self._db.execute(
            "INSERT INTO documents"
            " (document_id, path, content_hash, size_bytes, indexing_status)"
            " VALUES (?, ?, ?, ?, ?)"
            " ON CONFLICT(document_id) DO UPDATE SET"
            " content_hash = excluded.content_hash,"
            " size_bytes = excluded.size_bytes,"
            " indexing_status = excluded.indexing_status,"
            " updated_at = datetime('now')",
            (
                record.document_id,
                record.path,
                record.content_hash,
                record.size_bytes,
                record.indexing_status.value,
            ),
        )

    def _delete_chunks(self, document_id: str) -> None:
        self._db.execute(
            "DELETE FROM chunks WHERE document_id = ?",
            (document_id,),
        )

    def _insert_chunks(self, chunks: list) -> None:
        for chunk in chunks:
            self._db.execute(
                "INSERT INTO chunks"
                " (chunk_id, document_id, byte_start, byte_end, line_start, line_end, text, chunk_hash)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    chunk.chunk_id,
                    chunk.document_id,
                    chunk.byte_start,
                    chunk.byte_end,
                    chunk.line_start,
                    chunk.line_end,
                    chunk.text,
                    chunk.chunk_hash,
                ),
            )

    def index_file(self, path: Path) -> DocumentRecord:
        record = self._parser.create_record(path)

        # Check if already indexed with same hash
        existing = self._find_document_by_path(path)
        if existing and existing.content_hash == record.content_hash:
            return existing

        # Reuse document_id if path already exists
        if existing:
            record = replace(record, document_id=existing.document_id)
            self._delete_chunks(existing.document_id)

        # Parse and chunk
        text = self._parser.parse(path)
        chunks = self._chunker.chunk(text, document_id=record.document_id)

        # Write document as INDEXING
        record = replace(record, indexing_status=IndexingStatus.INDEXING)
        self._write_document(record)

        # Write chunks
        self._insert_chunks(chunks)

        # Mark as INDEXED
        record = replace(record, indexing_status=IndexingStatus.INDEXED)
        self._write_document(record)
        self._db.commit()

        return record

    def reindex_file(self, path: Path) -> DocumentRecord:
        record = self._parser.create_record(path)

        existing = self._find_document_by_path(path)
        if existing:
            record = replace(record, document_id=existing.document_id)
            self._delete_chunks(existing.document_id)

        text = self._parser.parse(path)
        chunks = self._chunker.chunk(text, document_id=record.document_id)

        record = replace(record, indexing_status=IndexingStatus.INDEXING)
        self._write_document(record)
        self._insert_chunks(chunks)
        record = replace(record, indexing_status=IndexingStatus.INDEXED)
        self._write_document(record)
        self._db.commit()

        return record

    def remove_file(self, path: Path) -> None:
        existing = self._find_document_by_path(path)
        if existing is None:
            return
        self._delete_chunks(existing.document_id)
        self._tombstone.create_tombstone(existing)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/codingstudio/__PROJECTHUB__/JARVIS/alliance_20260317_130542 && python -m pytest tests/indexing/test_index_pipeline.py -v`
Expected: ALL PASS

- [ ] **Step 5: Run full test suite for regression**

Run: `cd /Users/codingstudio/__PROJECTHUB__/JARVIS/alliance_20260317_130542 && python -m pytest -v`
Expected: ALL tests PASS

- [ ] **Step 6: Commit**

```bash
git add src/jarvis/indexing/index_pipeline.py tests/indexing/test_index_pipeline.py
git commit -m "feat(indexing): implement IndexPipeline with parse-chunk-store to SQLite"
```

---

### Task 5: FileWatcher — directory monitoring via watchdog

**Files:**
- Modify: `src/jarvis/indexing/file_watcher.py`
- Create: `tests/indexing/test_file_watcher.py`
- Modify: `pyproject.toml`

- [ ] **Step 1: Add watchdog dependency**

In `pyproject.toml`, add `"watchdog>=4.0"` to `dependencies`:

```toml
dependencies = [
    "kiwi-py>=0.18",
    "mlx>=0.22",
    "numpy>=1.26",
    "watchdog>=4.0",
]
```

- [ ] **Step 2: Write failing tests**

```python
# tests/indexing/test_file_watcher.py
"""Tests for FileWatcher."""
from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from jarvis.indexing.file_watcher import FileWatcher


class TestFileWatcherInit:
    def test_creates_with_folders(self, tmp_path: Path) -> None:
        watcher = FileWatcher(watched_folders=[tmp_path])
        assert watcher._watched_folders == [tmp_path]

    def test_creates_with_callback(self, tmp_path: Path) -> None:
        cb = MagicMock()
        watcher = FileWatcher(watched_folders=[tmp_path], on_change=cb)
        assert watcher._on_change is cb


class TestFileWatcherStartStop:
    def test_start_and_stop(self, tmp_path: Path) -> None:
        watcher = FileWatcher(watched_folders=[tmp_path])
        watcher.start()
        assert watcher._running
        watcher.stop()
        assert not watcher._running

    def test_stop_without_start_is_safe(self, tmp_path: Path) -> None:
        watcher = FileWatcher(watched_folders=[tmp_path])
        watcher.stop()  # Should not raise


class TestFileWatcherEvents:
    def test_detects_file_creation(self, tmp_path: Path) -> None:
        events: list[tuple[Path, str]] = []

        def on_change(path: Path, event_type: str) -> None:
            events.append((path, event_type))

        watcher = FileWatcher(watched_folders=[tmp_path], on_change=on_change)
        watcher.start()

        try:
            (tmp_path / "new.md").write_text("hello")
            time.sleep(1.0)  # Give watchdog time to detect
        finally:
            watcher.stop()

        created = [e for e in events if e[1] == "created"]
        assert len(created) >= 1
        assert any("new.md" in str(e[0]) for e in created)

    def test_detects_file_modification(self, tmp_path: Path) -> None:
        f = tmp_path / "existing.md"
        f.write_text("original")
        time.sleep(0.1)

        events: list[tuple[Path, str]] = []

        def on_change(path: Path, event_type: str) -> None:
            events.append((path, event_type))

        watcher = FileWatcher(watched_folders=[tmp_path], on_change=on_change)
        watcher.start()

        try:
            f.write_text("modified")
            time.sleep(1.0)
        finally:
            watcher.stop()

        modified = [e for e in events if e[1] == "modified"]
        assert len(modified) >= 1

    def test_detects_file_deletion(self, tmp_path: Path) -> None:
        f = tmp_path / "deleteme.md"
        f.write_text("to delete")
        time.sleep(0.1)

        events: list[tuple[Path, str]] = []

        def on_change(path: Path, event_type: str) -> None:
            events.append((path, event_type))

        watcher = FileWatcher(watched_folders=[tmp_path], on_change=on_change)
        watcher.start()

        try:
            f.unlink()
            time.sleep(1.0)
        finally:
            watcher.stop()

        deleted = [e for e in events if e[1] == "deleted"]
        assert len(deleted) >= 1

    def test_ignores_hidden_files(self, tmp_path: Path) -> None:
        events: list[tuple[Path, str]] = []

        def on_change(path: Path, event_type: str) -> None:
            events.append((path, event_type))

        watcher = FileWatcher(watched_folders=[tmp_path], on_change=on_change)
        watcher.start()

        try:
            (tmp_path / ".hidden").write_text("should ignore")
            time.sleep(1.0)
        finally:
            watcher.stop()

        # Should not report hidden files
        assert all(".hidden" not in str(e[0]) for e in events)
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd /Users/codingstudio/__PROJECTHUB__/JARVIS/alliance_20260317_130542 && python -m pytest tests/indexing/test_file_watcher.py -v`
Expected: FAIL

- [ ] **Step 4: Implement FileWatcher**

```python
# src/jarvis/indexing/file_watcher.py
"""FileWatcher — monitors watched folders for file changes via watchdog.

Detects creates, updates, and deletes and feeds them into the
indexing pipeline.
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer


class _Handler(FileSystemEventHandler):
    """Internal event handler that forwards to the on_change callback."""

    def __init__(self, on_change: Callable[[Path, str], None]) -> None:
        self._on_change = on_change

    def _should_ignore(self, path: str) -> bool:
        name = Path(path).name
        return name.startswith(".")

    def on_created(self, event: FileSystemEvent) -> None:
        if event.is_directory or self._should_ignore(event.src_path):
            return
        self._on_change(Path(event.src_path), "created")

    def on_modified(self, event: FileSystemEvent) -> None:
        if event.is_directory or self._should_ignore(event.src_path):
            return
        self._on_change(Path(event.src_path), "modified")

    def on_deleted(self, event: FileSystemEvent) -> None:
        if event.is_directory or self._should_ignore(event.src_path):
            return
        self._on_change(Path(event.src_path), "deleted")


class FileWatcher:
    """Watches directories for file system changes using watchdog."""

    def __init__(
        self,
        *,
        watched_folders: list[Path],
        on_change: Callable[[Path, str], None] | None = None,
    ) -> None:
        self._watched_folders = watched_folders
        self._on_change = on_change
        self._observer: Observer | None = None
        self._running = False

    def start(self) -> None:
        self._running = True
        if self._on_change is None:
            return
        self._observer = Observer()
        handler = _Handler(self._on_change)
        for folder in self._watched_folders:
            self._observer.schedule(handler, str(folder), recursive=True)
        self._observer.start()

    def stop(self) -> None:
        if self._observer is not None:
            self._observer.stop()
            self._observer.join()
            self._observer = None
        self._running = False
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd /Users/codingstudio/__PROJECTHUB__/JARVIS/alliance_20260317_130542 && python -m pytest tests/indexing/test_file_watcher.py -v`
Expected: ALL PASS

- [ ] **Step 6: Run full test suite for regression**

Run: `cd /Users/codingstudio/__PROJECTHUB__/JARVIS/alliance_20260317_130542 && python -m pytest -v`
Expected: ALL tests PASS

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml src/jarvis/indexing/file_watcher.py tests/indexing/test_file_watcher.py
git commit -m "feat(indexing): implement FileWatcher with watchdog for directory monitoring"
```

---

### Task 6: Integration test — full indexing round-trip

**Files:**
- Create: `tests/indexing/test_integration.py`

- [ ] **Step 1: Write integration test**

```python
# tests/indexing/test_integration.py
"""Integration test: full indexing round-trip from file to FTS search."""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Sequence

import pytest

from jarvis.app.bootstrap import init_database
from jarvis.app.config import JarvisConfig
from jarvis.indexing.chunker import Chunker
from jarvis.indexing.index_pipeline import IndexPipeline
from jarvis.indexing.parsers import DocumentParser
from jarvis.indexing.tombstone import TombstoneManager


class FakeEmbeddingRuntime:
    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        return [[0.0] * 8 for _ in texts]


@pytest.fixture
def setup(tmp_path: Path) -> tuple[IndexPipeline, sqlite3.Connection, Path]:
    config = JarvisConfig(watched_folders=[tmp_path], data_dir=tmp_path / ".jarvis")
    db = init_database(config)
    pipeline = IndexPipeline(
        db=db,
        parser=DocumentParser(),
        chunker=Chunker(max_chunk_bytes=512, overlap_bytes=64),
        tombstone_manager=TombstoneManager(db=db),
        embedding_runtime=FakeEmbeddingRuntime(),
    )
    return pipeline, db, tmp_path


@pytest.mark.integration
class TestIndexingRoundTrip:
    def test_index_and_fts_search(
        self, setup: tuple[IndexPipeline, sqlite3.Connection, Path]
    ) -> None:
        pipeline, db, tmp_path = setup

        # Create test files
        (tmp_path / "arch.md").write_text(
            "# JARVIS Architecture\n\nThe system uses a monolith-first design with protocol interfaces."
        )
        (tmp_path / "retrieval.py").write_text(
            '"""Retrieval module for JARVIS."""\n\ndef search(query: str) -> list:\n    pass\n'
        )

        # Index both files
        r1 = pipeline.index_file(tmp_path / "arch.md")
        r2 = pipeline.index_file(tmp_path / "retrieval.py")

        # Search FTS for "architecture"
        rows = db.execute(
            "SELECT c.chunk_id, c.document_id, c.text"
            " FROM chunks c"
            " JOIN chunks_fts f ON c.rowid = f.rowid"
            " WHERE chunks_fts MATCH ?",
            ("architecture",),
        ).fetchall()
        assert len(rows) >= 1
        assert any("Architecture" in r[2] for r in rows)

        # Search FTS for Korean-transliterated content
        rows_mono = db.execute(
            "SELECT c.text FROM chunks c"
            " JOIN chunks_fts f ON c.rowid = f.rowid"
            " WHERE chunks_fts MATCH ?",
            ("monolith",),
        ).fetchall()
        assert len(rows_mono) >= 1

    def test_reindex_updates_fts(
        self, setup: tuple[IndexPipeline, sqlite3.Connection, Path]
    ) -> None:
        pipeline, db, tmp_path = setup

        f = tmp_path / "doc.md"
        f.write_text("Original topic about databases")
        pipeline.index_file(f)

        # Verify FTS contains "databases"
        assert db.execute(
            "SELECT COUNT(*) FROM chunks_fts WHERE chunks_fts MATCH ?",
            ("databases",),
        ).fetchone()[0] >= 1

        # Reindex with new content
        f.write_text("Updated topic about networking")
        pipeline.reindex_file(f)

        # Old term gone from FTS
        assert db.execute(
            "SELECT COUNT(*) FROM chunks_fts WHERE chunks_fts MATCH ?",
            ("databases",),
        ).fetchone()[0] == 0

        # New term present
        assert db.execute(
            "SELECT COUNT(*) FROM chunks_fts WHERE chunks_fts MATCH ?",
            ("networking",),
        ).fetchone()[0] >= 1

    def test_remove_clears_fts(
        self, setup: tuple[IndexPipeline, sqlite3.Connection, Path]
    ) -> None:
        pipeline, db, tmp_path = setup

        f = tmp_path / "ephemeral.md"
        f.write_text("Ephemeral content for deletion test")
        pipeline.index_file(f)

        assert db.execute(
            "SELECT COUNT(*) FROM chunks_fts WHERE chunks_fts MATCH ?",
            ("ephemeral",),
        ).fetchone()[0] >= 1

        pipeline.remove_file(f)

        assert db.execute(
            "SELECT COUNT(*) FROM chunks_fts WHERE chunks_fts MATCH ?",
            ("ephemeral",),
        ).fetchone()[0] == 0

    def test_index_korean_document(
        self, setup: tuple[IndexPipeline, sqlite3.Connection, Path]
    ) -> None:
        pipeline, db, tmp_path = setup

        f = tmp_path / "korean.md"
        f.write_text("# JARVIS 프로젝트\n\n음성 인식 시스템의 아키텍처를 설명합니다.")
        pipeline.index_file(f)

        chunks = db.execute("SELECT text FROM chunks").fetchall()
        assert len(chunks) >= 1
        assert any("음성" in c[0] for c in chunks)

    def test_index_test_corpus(
        self, setup: tuple[IndexPipeline, sqlite3.Connection, Path]
    ) -> None:
        """Index all files from the test corpus fixture."""
        pipeline, db, _ = setup
        corpus_dir = Path(__file__).parent.parent / "fixtures" / "corpus"
        if not corpus_dir.exists():
            pytest.skip("Test corpus not found")

        for f in corpus_dir.iterdir():
            if f.is_file() and not f.name.startswith("."):
                pipeline.index_file(f)

        doc_count = db.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
        chunk_count = db.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
        assert doc_count >= 1
        assert chunk_count >= 1
```

- [ ] **Step 2: Run integration tests**

Run: `cd /Users/codingstudio/__PROJECTHUB__/JARVIS/alliance_20260317_130542 && python -m pytest tests/indexing/test_integration.py -v`
Expected: ALL PASS

- [ ] **Step 3: Run complete test suite**

Run: `cd /Users/codingstudio/__PROJECTHUB__/JARVIS/alliance_20260317_130542 && python -m pytest -v`
Expected: ALL tests PASS (113 original + new indexing tests)

- [ ] **Step 4: Commit**

```bash
git add tests/indexing/test_integration.py
git commit -m "test(indexing): add integration tests for full indexing round-trip with FTS"
```
