# Retrieval Pipeline Implementation Plan

> **Status note (2026-03-25):** This is a historical implementation plan. The current runtime no longer uses `db=None` stub evidence/search behavior; when retrieval state is unavailable it returns empty results, and evidence-gated factual answering stays disabled until indexed evidence exists.

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the retrieval pipeline: QueryDecomposer (language detection), FTSIndex (real SQLite FTS5 queries), FreshnessChecker, enhanced EvidenceBuilder — enabling JARVIS to search indexed documents and build grounded evidence for answers.

**Architecture:** QueryDecomposer detects language (Korean/English/code) and splits queries into typed fragments. FTSIndex queries SQLite FTS5 with BM25 ranking. VectorIndex stays as an improved stub (real embedding model not yet available). HybridSearch (already implemented) fuses results via RRF. EvidenceBuilder resolves chunks from DB and verifies citation freshness. All constructors accept optional `db` parameter — when `None`, backward-compatible stub behavior is preserved for existing 168 tests.

**Tech Stack:** Python 3.12, SQLite FTS5, kiwi-py (Korean morphological analysis), re (regex for language detection)

---

## File Structure

| Action | Path | Responsibility |
|--------|------|----------------|
| Modify | `src/jarvis/retrieval/tokenizer_kiwi.py` | Korean morphological tokenizer via Kiwi |
| Modify | `src/jarvis/retrieval/query_decomposer.py` | Language detection + query decomposition |
| Modify | `src/jarvis/retrieval/fts_index.py` | Real SQLite FTS5 search with BM25 |
| Modify | `src/jarvis/retrieval/vector_index.py` | Improved stub, ready for embeddings |
| Modify | `src/jarvis/retrieval/freshness.py` | Citation freshness validation against DB |
| Modify | `src/jarvis/retrieval/evidence_builder.py` | Resolve chunks from DB, freshness checks |
| Create | `tests/retrieval/test_tokenizer_kiwi.py` | Kiwi tokenizer tests |
| Create | `tests/retrieval/test_query_decomposer.py` | Query decomposition tests |
| Create | `tests/retrieval/test_fts_index.py` | FTS search tests |
| Create | `tests/retrieval/test_freshness.py` | Freshness checker tests |
| Create | `tests/retrieval/test_evidence_builder.py` | Evidence builder tests |
| Create | `tests/retrieval/test_retrieval_integration.py` | Full retrieval round-trip |

---

### Task 1: KiwiTokenizer — Korean morphological tokenizer

**Files:**
- Modify: `src/jarvis/retrieval/tokenizer_kiwi.py`
- Create: `tests/retrieval/test_tokenizer_kiwi.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/retrieval/test_tokenizer_kiwi.py
"""Tests for KiwiTokenizer."""
from __future__ import annotations

from jarvis.retrieval.tokenizer_kiwi import KiwiTokenizer


class TestKiwiTokenizer:
    def test_tokenize_korean(self) -> None:
        t = KiwiTokenizer()
        tokens = t.tokenize("프로젝트 아키텍처를 설명해줘")
        assert len(tokens) > 0
        assert all(isinstance(tok, str) for tok in tokens)

    def test_tokenize_english_passthrough(self) -> None:
        t = KiwiTokenizer()
        tokens = t.tokenize("architecture design")
        assert len(tokens) > 0

    def test_tokenize_empty(self) -> None:
        t = KiwiTokenizer()
        assert t.tokenize("") == []

    def test_tokenize_for_fts(self) -> None:
        t = KiwiTokenizer()
        result = t.tokenize_for_fts("음성 인식 시스템")
        assert isinstance(result, str)
        assert len(result) > 0
        # Should be space-separated tokens
        assert " " in result or len(result.split()) >= 1

    def test_tokenize_mixed(self) -> None:
        t = KiwiTokenizer()
        tokens = t.tokenize("JARVIS 프로젝트의 아키텍처")
        assert len(tokens) > 0
```

- [ ] **Step 2: Implement KiwiTokenizer**

```python
# src/jarvis/retrieval/tokenizer_kiwi.py
"""KiwiTokenizer — Korean morphological tokenizer wrapper.

Wraps the Kiwi tokenizer for Korean text segmentation,
producing tokens suitable for FTS5 indexing.
"""
from __future__ import annotations

from kiwipiepy import Kiwi


class KiwiTokenizer:
    """Korean morphological tokenizer using Kiwi."""

    def __init__(self) -> None:
        self._kiwi = Kiwi()

    def tokenize(self, text: str) -> list[str]:
        if not text.strip():
            return []
        result = self._kiwi.tokenize(text)
        return [token.form for token in result if token.form.strip()]

    def tokenize_for_fts(self, text: str) -> str:
        tokens = self.tokenize(text)
        return " ".join(tokens)
```

- [ ] **Step 3: Run tests, verify pass**
- [ ] **Step 4: Run full suite, verify no regressions**
- [ ] **Step 5: Commit**

```bash
git add src/jarvis/retrieval/tokenizer_kiwi.py tests/retrieval/test_tokenizer_kiwi.py
git commit -m "feat(retrieval): implement KiwiTokenizer for Korean morphological analysis"
```

---

### Task 2: QueryDecomposer — language detection + decomposition

**Files:**
- Modify: `src/jarvis/retrieval/query_decomposer.py`
- Create: `tests/retrieval/test_query_decomposer.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/retrieval/test_query_decomposer.py
"""Tests for QueryDecomposer."""
from __future__ import annotations

from jarvis.contracts import TypedQueryFragment
from jarvis.retrieval.query_decomposer import QueryDecomposer


class TestQueryDecomposer:
    def test_korean_query(self) -> None:
        fragments = QueryDecomposer().decompose("프로젝트 아키텍처를 설명해줘")
        assert len(fragments) >= 1
        assert all(isinstance(f, TypedQueryFragment) for f in fragments)
        # Should detect Korean
        assert any(f.language == "ko" for f in fragments)

    def test_english_query(self) -> None:
        fragments = QueryDecomposer().decompose("explain the architecture")
        assert len(fragments) >= 1
        assert any(f.language == "en" for f in fragments)

    def test_code_query(self) -> None:
        fragments = QueryDecomposer().decompose("def search_files(query)")
        assert len(fragments) >= 1
        assert any(f.language == "code" for f in fragments)

    def test_mixed_query(self) -> None:
        fragments = QueryDecomposer().decompose("JARVIS 프로젝트의 architecture를 보여줘")
        assert len(fragments) >= 1
        # Should produce both keyword and semantic fragments
        types = {f.query_type for f in fragments}
        assert "keyword" in types

    def test_empty_query(self) -> None:
        fragments = QueryDecomposer().decompose("")
        assert fragments == []

    def test_fragments_have_weight(self) -> None:
        fragments = QueryDecomposer().decompose("검색 시스템 구조")
        for f in fragments:
            assert f.weight > 0.0

    def test_protocol_conformance(self) -> None:
        from jarvis.contracts import QueryDecomposerProtocol
        assert isinstance(QueryDecomposer(), QueryDecomposerProtocol)
```

- [ ] **Step 2: Implement QueryDecomposer**

```python
# src/jarvis/retrieval/query_decomposer.py
"""QueryDecomposer — decomposes user queries into typed fragments.

Splits mixed Korean/English/code queries into TypedQueryFragment
objects for downstream FTS and vector retrieval.
"""
from __future__ import annotations

import re

from jarvis.contracts import TypedQueryFragment


_KOREAN_RE = re.compile(r"[\uac00-\ud7af\u1100-\u11ff\u3130-\u318f]+")
_CODE_RE = re.compile(
    r"(?:def |class |import |from |function |const |let |var |=>|->|\(\)|\.py|\.ts|\.js)"
)


def _detect_language(text: str) -> str:
    """Detect primary language of text: 'ko', 'en', or 'code'."""
    if _CODE_RE.search(text):
        return "code"
    korean_chars = len(_KOREAN_RE.findall(text))
    ascii_words = len(re.findall(r"[a-zA-Z]+", text))
    if korean_chars > ascii_words:
        return "ko"
    if ascii_words > 0 and korean_chars == 0:
        return "en"
    return "ko"  # default for mixed


class QueryDecomposer:
    """Decomposes a user query into typed fragments for retrieval."""

    def decompose(self, query: str) -> list[TypedQueryFragment]:
        if not query.strip():
            return []

        language = _detect_language(query)
        fragments: list[TypedQueryFragment] = []

        # Primary: keyword fragment for FTS
        fragments.append(TypedQueryFragment(
            text=query,
            language=language,
            query_type="keyword",
            weight=1.0,
        ))

        # Secondary: semantic fragment for vector search (lower weight)
        fragments.append(TypedQueryFragment(
            text=query,
            language=language,
            query_type="semantic",
            weight=0.7,
        ))

        return fragments
```

- [ ] **Step 3: Run tests, verify pass**
- [ ] **Step 4: Run full suite, verify no regressions (including E2E smoke tests)**
- [ ] **Step 5: Commit**

```bash
git add src/jarvis/retrieval/query_decomposer.py tests/retrieval/test_query_decomposer.py
git commit -m "feat(retrieval): implement QueryDecomposer with language detection"
```

---

### Task 3: FTSIndex — real SQLite FTS5 search

**Files:**
- Modify: `src/jarvis/retrieval/fts_index.py`
- Create: `tests/retrieval/test_fts_index.py`

**CRITICAL:** Constructor must remain callable with no args for backward compatibility with E2E smoke tests. When `db=None`, return stub results.

- [ ] **Step 1: Write failing tests**

```python
# tests/retrieval/test_fts_index.py
"""Tests for FTSIndex."""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Sequence

import pytest

from jarvis.app.bootstrap import init_database
from jarvis.app.config import JarvisConfig
from jarvis.contracts import SearchHit, TypedQueryFragment
from jarvis.indexing.chunker import Chunker
from jarvis.indexing.index_pipeline import IndexPipeline
from jarvis.indexing.parsers import DocumentParser
from jarvis.indexing.tombstone import TombstoneManager
from jarvis.retrieval.fts_index import FTSIndex


class FakeEmbeddingRuntime:
    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        return [[0.0] * 8 for _ in texts]


@pytest.fixture
def indexed_db(tmp_path: Path) -> sqlite3.Connection:
    config = JarvisConfig(watched_folders=[tmp_path], data_dir=tmp_path / ".jarvis")
    db = init_database(config)
    pipeline = IndexPipeline(
        db=db,
        parser=DocumentParser(),
        chunker=Chunker(max_chunk_bytes=512, overlap_bytes=64),
        tombstone_manager=TombstoneManager(db=db),
        embedding_runtime=FakeEmbeddingRuntime(),
    )
    (tmp_path / "arch.md").write_text(
        "# JARVIS Architecture\n\nThe system uses a monolith-first design with protocol interfaces."
    )
    (tmp_path / "korean.md").write_text(
        "# JARVIS 프로젝트\n\n음성 인식 시스템의 아키텍처를 설명합니다."
    )
    (tmp_path / "code.py").write_text(
        '"""Search module."""\n\ndef search_files(query: str) -> list:\n    pass\n'
    )
    pipeline.index_file(tmp_path / "arch.md")
    pipeline.index_file(tmp_path / "korean.md")
    pipeline.index_file(tmp_path / "code.py")
    return db


class TestFTSIndexNoDb:
    """Backward compatibility: no db returns stub results."""

    def test_stub_returns_hit(self) -> None:
        fts = FTSIndex()
        fragments = [TypedQueryFragment(text="test", language="en", query_type="keyword")]
        hits = fts.search(fragments)
        assert len(hits) >= 1
        assert isinstance(hits[0], SearchHit)


class TestFTSIndexWithDb:
    def test_search_english(self, indexed_db: sqlite3.Connection) -> None:
        fts = FTSIndex(db=indexed_db)
        fragments = [TypedQueryFragment(text="architecture", language="en", query_type="keyword")]
        hits = fts.search(fragments)
        assert len(hits) >= 1
        assert any("Architecture" in h.snippet or "architecture" in h.snippet.lower() for h in hits)

    def test_search_korean(self, indexed_db: sqlite3.Connection) -> None:
        fts = FTSIndex(db=indexed_db)
        fragments = [TypedQueryFragment(text="음성 인식", language="ko", query_type="keyword")]
        hits = fts.search(fragments)
        assert len(hits) >= 1

    def test_search_no_results(self, indexed_db: sqlite3.Connection) -> None:
        fts = FTSIndex(db=indexed_db)
        fragments = [TypedQueryFragment(text="xyznonexistent", language="en", query_type="keyword")]
        hits = fts.search(fragments)
        assert hits == []

    def test_search_respects_top_k(self, indexed_db: sqlite3.Connection) -> None:
        fts = FTSIndex(db=indexed_db)
        fragments = [TypedQueryFragment(text="JARVIS", language="en", query_type="keyword")]
        hits = fts.search(fragments, top_k=1)
        assert len(hits) <= 1

    def test_hits_have_byte_ranges(self, indexed_db: sqlite3.Connection) -> None:
        fts = FTSIndex(db=indexed_db)
        fragments = [TypedQueryFragment(text="monolith", language="en", query_type="keyword")]
        hits = fts.search(fragments)
        if hits:
            assert hits[0].byte_range is not None
            assert hits[0].line_range is not None

    def test_multiple_fragments(self, indexed_db: sqlite3.Connection) -> None:
        fts = FTSIndex(db=indexed_db)
        fragments = [
            TypedQueryFragment(text="architecture", language="en", query_type="keyword"),
            TypedQueryFragment(text="design", language="en", query_type="keyword"),
        ]
        hits = fts.search(fragments)
        assert len(hits) >= 1
```

- [ ] **Step 2: Implement FTSIndex**

```python
# src/jarvis/retrieval/fts_index.py
"""FTSIndex — full-text search retrieval via SQLite FTS5.

Implements FTSRetrieverProtocol for BM25-based full-text search
over indexed document chunks.
"""
from __future__ import annotations

import sqlite3
from typing import Sequence

from jarvis.contracts import SearchHit, TypedQueryFragment


class FTSIndex:
    """Full-text search index backed by SQLite FTS5."""

    def __init__(self, *, db: sqlite3.Connection | None = None) -> None:
        self._db = db

    def search(
        self, fragments: Sequence[TypedQueryFragment], top_k: int = 10
    ) -> list[SearchHit]:
        if self._db is None:
            return self._stub_search()

        # Build FTS5 query from keyword fragments
        terms: list[str] = []
        for frag in fragments:
            if frag.query_type == "keyword":
                # Escape FTS5 special characters and split into words
                words = frag.text.split()
                terms.extend(w for w in words if w.strip())

        if not terms:
            return []

        # Join terms with OR for broader matching
        fts_query = " OR ".join(f'"{t}"' for t in terms)

        try:
            rows = self._db.execute(
                "SELECT c.chunk_id, c.document_id, c.text, c.byte_start, c.byte_end,"
                " c.line_start, c.line_end, rank"
                " FROM chunks c"
                " JOIN chunks_fts f ON c.rowid = f.rowid"
                " WHERE chunks_fts MATCH ?"
                " ORDER BY rank"
                " LIMIT ?",
                (fts_query, top_k),
            ).fetchall()
        except sqlite3.OperationalError:
            return []

        hits: list[SearchHit] = []
        for row in rows:
            hits.append(SearchHit(
                chunk_id=row[0],
                document_id=row[1],
                score=abs(row[7]) if row[7] else 0.0,  # FTS5 rank is negative
                snippet=row[2][:200] if row[2] else "",
                byte_range=(row[3], row[4]),
                line_range=(row[5], row[6]),
            ))
        return hits

    def _stub_search(self) -> list[SearchHit]:
        """Phase 0 backward-compatible stub."""
        return [
            SearchHit(
                chunk_id="stub-chunk-1",
                document_id="stub-doc-1",
                score=0.95,
                snippet="stub FTS result",
            ),
        ]
```

- [ ] **Step 3: Run tests, verify pass**
- [ ] **Step 4: Run full suite (168 existing tests must still pass)**
- [ ] **Step 5: Commit**

```bash
git add src/jarvis/retrieval/fts_index.py tests/retrieval/test_fts_index.py
git commit -m "feat(retrieval): implement FTSIndex with real SQLite FTS5 BM25 search"
```

---

### Task 4: FreshnessChecker — citation freshness validation

**Files:**
- Modify: `src/jarvis/retrieval/freshness.py`
- Create: `tests/retrieval/test_freshness.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/retrieval/test_freshness.py
"""Tests for FreshnessChecker."""
from __future__ import annotations

from jarvis.contracts import (
    CitationRecord,
    CitationState,
    DocumentRecord,
    IndexingStatus,
    AccessStatus,
)
from jarvis.retrieval.freshness import FreshnessChecker


class TestFreshnessChecker:
    def test_indexed_accessible_is_valid(self) -> None:
        checker = FreshnessChecker()
        citation = CitationRecord(document_id="d1", chunk_id="c1", label="[1]")
        doc = DocumentRecord(
            document_id="d1", path="/tmp/f.md",
            indexing_status=IndexingStatus.INDEXED,
            access_status=AccessStatus.ACCESSIBLE,
        )
        assert checker.check(citation, doc) == CitationState.VALID

    def test_tombstoned_is_missing(self) -> None:
        checker = FreshnessChecker()
        citation = CitationRecord(document_id="d1", chunk_id="c1", label="[1]")
        doc = DocumentRecord(
            document_id="d1", path="/tmp/f.md",
            indexing_status=IndexingStatus.TOMBSTONED,
        )
        assert checker.check(citation, doc) == CitationState.MISSING

    def test_reindexing_is_reindexing(self) -> None:
        checker = FreshnessChecker()
        citation = CitationRecord(document_id="d1", chunk_id="c1", label="[1]")
        doc = DocumentRecord(
            document_id="d1", path="/tmp/f.md",
            indexing_status=IndexingStatus.INDEXING,
        )
        assert checker.check(citation, doc) == CitationState.REINDEXING

    def test_access_denied_is_access_lost(self) -> None:
        checker = FreshnessChecker()
        citation = CitationRecord(document_id="d1", chunk_id="c1", label="[1]")
        doc = DocumentRecord(
            document_id="d1", path="/tmp/f.md",
            indexing_status=IndexingStatus.INDEXED,
            access_status=AccessStatus.DENIED,
        )
        assert checker.check(citation, doc) == CitationState.ACCESS_LOST

    def test_not_found_is_access_lost(self) -> None:
        checker = FreshnessChecker()
        citation = CitationRecord(document_id="d1", chunk_id="c1", label="[1]")
        doc = DocumentRecord(
            document_id="d1", path="/tmp/f.md",
            access_status=AccessStatus.NOT_FOUND,
        )
        assert checker.check(citation, doc) == CitationState.ACCESS_LOST

    def test_failed_indexing_is_stale(self) -> None:
        checker = FreshnessChecker()
        citation = CitationRecord(document_id="d1", chunk_id="c1", label="[1]")
        doc = DocumentRecord(
            document_id="d1", path="/tmp/f.md",
            indexing_status=IndexingStatus.FAILED,
        )
        assert checker.check(citation, doc) == CitationState.STALE

    def test_refresh_citation(self) -> None:
        checker = FreshnessChecker()
        citation = CitationRecord(
            document_id="d1", chunk_id="c1", label="[1]",
            state=CitationState.VALID,
        )
        doc = DocumentRecord(
            document_id="d1", path="/tmp/f.md",
            indexing_status=IndexingStatus.TOMBSTONED,
        )
        refreshed = checker.refresh_citation(citation, doc)
        assert refreshed.state == CitationState.MISSING
        assert refreshed.citation_id == citation.citation_id
```

- [ ] **Step 2: Implement FreshnessChecker**

```python
# src/jarvis/retrieval/freshness.py
"""FreshnessChecker — validates citation freshness states.

Checks whether indexed documents are still current by comparing
indexing/access status, and updates CitationState accordingly.
"""
from __future__ import annotations

from dataclasses import replace

from jarvis.contracts import (
    AccessStatus,
    CitationRecord,
    CitationState,
    DocumentRecord,
    IndexingStatus,
)


class FreshnessChecker:
    """Validates and updates citation freshness for evidence items."""

    def check(self, citation: CitationRecord, document: DocumentRecord) -> CitationState:
        # Access denied or not found → ACCESS_LOST
        if document.access_status in (AccessStatus.DENIED, AccessStatus.NOT_FOUND):
            return CitationState.ACCESS_LOST

        # Tombstoned → MISSING
        if document.indexing_status == IndexingStatus.TOMBSTONED:
            return CitationState.MISSING

        # Currently re-indexing → REINDEXING
        if document.indexing_status == IndexingStatus.INDEXING:
            return CitationState.REINDEXING

        # Failed indexing → STALE
        if document.indexing_status == IndexingStatus.FAILED:
            return CitationState.STALE

        # Indexed and accessible → VALID
        return CitationState.VALID

    def refresh_citation(
        self, citation: CitationRecord, document: DocumentRecord
    ) -> CitationRecord:
        new_state = self.check(citation, document)
        return replace(citation, state=new_state)
```

- [ ] **Step 3: Run tests, verify pass**
- [ ] **Step 4: Run full suite**
- [ ] **Step 5: Commit**

```bash
git add src/jarvis/retrieval/freshness.py tests/retrieval/test_freshness.py
git commit -m "feat(retrieval): implement FreshnessChecker for citation state validation"
```

---

### Task 5: EvidenceBuilder — resolve chunks from DB with freshness

**Files:**
- Modify: `src/jarvis/retrieval/evidence_builder.py`
- Create: `tests/retrieval/test_evidence_builder.py`

**CRITICAL:** Constructor must remain callable with no args for smoke test compatibility.

- [ ] **Step 1: Write failing tests**

```python
# tests/retrieval/test_evidence_builder.py
"""Tests for EvidenceBuilder."""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Sequence

import pytest

from jarvis.app.bootstrap import init_database
from jarvis.app.config import JarvisConfig
from jarvis.contracts import (
    CitationState,
    EvidenceBuilderProtocol,
    HybridSearchResult,
    TypedQueryFragment,
    VerifiedEvidenceSet,
)
from jarvis.indexing.chunker import Chunker
from jarvis.indexing.index_pipeline import IndexPipeline
from jarvis.indexing.parsers import DocumentParser
from jarvis.indexing.tombstone import TombstoneManager
from jarvis.retrieval.evidence_builder import EvidenceBuilder


class FakeEmbeddingRuntime:
    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        return [[0.0] * 8 for _ in texts]


@pytest.fixture
def indexed_setup(tmp_path: Path) -> tuple[sqlite3.Connection, str, str]:
    """Returns (db, document_id, chunk_id) for a known indexed document."""
    config = JarvisConfig(watched_folders=[tmp_path], data_dir=tmp_path / ".jarvis")
    db = init_database(config)
    pipeline = IndexPipeline(
        db=db,
        parser=DocumentParser(),
        chunker=Chunker(max_chunk_bytes=512, overlap_bytes=64),
        tombstone_manager=TombstoneManager(db=db),
        embedding_runtime=FakeEmbeddingRuntime(),
    )
    (tmp_path / "doc.md").write_text("Architecture design for JARVIS project.")
    record = pipeline.index_file(tmp_path / "doc.md")
    chunk_row = db.execute(
        "SELECT chunk_id FROM chunks WHERE document_id = ?",
        (record.document_id,),
    ).fetchone()
    return db, record.document_id, chunk_row[0]


class TestEvidenceBuilderNoDb:
    """Backward compatible: no db."""

    def test_stub_builds_evidence(self) -> None:
        builder = EvidenceBuilder()
        results = [HybridSearchResult(
            chunk_id="c1", document_id="d1", rrf_score=0.5, snippet="text",
        )]
        fragments = [TypedQueryFragment(text="q", language="ko", query_type="keyword")]
        evidence = builder.build(results, fragments)
        assert not evidence.is_empty
        assert evidence.items[0].citation.label == "[1]"

    def test_empty_results(self) -> None:
        builder = EvidenceBuilder()
        evidence = builder.build(
            [], [TypedQueryFragment(text="q", language="ko", query_type="keyword")]
        )
        assert evidence.is_empty

    def test_protocol_conformance(self) -> None:
        assert isinstance(EvidenceBuilder(), EvidenceBuilderProtocol)


class TestEvidenceBuilderWithDb:
    def test_resolves_chunk_text_from_db(
        self, indexed_setup: tuple[sqlite3.Connection, str, str]
    ) -> None:
        db, doc_id, chunk_id = indexed_setup
        builder = EvidenceBuilder(db=db)
        results = [HybridSearchResult(
            chunk_id=chunk_id, document_id=doc_id, rrf_score=0.5, snippet="",
        )]
        fragments = [TypedQueryFragment(text="arch", language="en", query_type="keyword")]
        evidence = builder.build(results, fragments)
        assert not evidence.is_empty
        # Should have resolved text from DB, not empty snippet
        assert "Architecture" in evidence.items[0].text or "design" in evidence.items[0].text

    def test_sets_source_path(
        self, indexed_setup: tuple[sqlite3.Connection, str, str]
    ) -> None:
        db, doc_id, chunk_id = indexed_setup
        builder = EvidenceBuilder(db=db)
        results = [HybridSearchResult(
            chunk_id=chunk_id, document_id=doc_id, rrf_score=0.5,
        )]
        fragments = [TypedQueryFragment(text="q", language="en", query_type="keyword")]
        evidence = builder.build(results, fragments)
        assert evidence.items[0].source_path  # non-empty

    def test_freshness_check_valid(
        self, indexed_setup: tuple[sqlite3.Connection, str, str]
    ) -> None:
        db, doc_id, chunk_id = indexed_setup
        builder = EvidenceBuilder(db=db)
        results = [HybridSearchResult(
            chunk_id=chunk_id, document_id=doc_id, rrf_score=0.5,
        )]
        fragments = [TypedQueryFragment(text="q", language="en", query_type="keyword")]
        evidence = builder.build(results, fragments)
        assert evidence.items[0].citation.state == CitationState.VALID

    def test_rejects_unresolvable_chunk(
        self, indexed_setup: tuple[sqlite3.Connection, str, str]
    ) -> None:
        db, doc_id, _ = indexed_setup
        builder = EvidenceBuilder(db=db)
        results = [HybridSearchResult(
            chunk_id="nonexistent-chunk", document_id=doc_id, rrf_score=0.5,
        )]
        fragments = [TypedQueryFragment(text="q", language="en", query_type="keyword")]
        evidence = builder.build(results, fragments)
        assert evidence.is_empty  # unresolvable items rejected
```

- [ ] **Step 2: Implement EvidenceBuilder**

```python
# src/jarvis/retrieval/evidence_builder.py
"""EvidenceBuilder — builds verified evidence sets from ranked search results.

Implements EvidenceBuilderProtocol. When db is provided, resolves chunk text
and verifies citation freshness. Without db, falls back to stub behavior.
"""
from __future__ import annotations

import sqlite3
from typing import Sequence

from jarvis.contracts import (
    CitationRecord,
    CitationState,
    DocumentRecord,
    EvidenceItem,
    HybridSearchResult,
    IndexingStatus,
    TypedQueryFragment,
    VerifiedEvidenceSet,
)
from jarvis.retrieval.freshness import FreshnessChecker


class EvidenceBuilder:
    """Builds VerifiedEvidenceSet from hybrid search results."""

    def __init__(self, *, db: sqlite3.Connection | None = None) -> None:
        self._db = db
        self._freshness = FreshnessChecker()

    def build(
        self,
        results: Sequence[HybridSearchResult],
        fragments: Sequence[TypedQueryFragment],
    ) -> VerifiedEvidenceSet:
        if not results:
            return VerifiedEvidenceSet(items=(), query_fragments=tuple(fragments))

        if self._db is None:
            return self._stub_build(results, fragments)

        items: list[EvidenceItem] = []
        for i, result in enumerate(results, 1):
            # Resolve chunk text from DB
            chunk_row = self._db.execute(
                "SELECT text FROM chunks WHERE chunk_id = ?",
                (result.chunk_id,),
            ).fetchone()
            if chunk_row is None:
                continue  # reject unresolvable

            # Resolve document for freshness check
            doc_row = self._db.execute(
                "SELECT document_id, path, content_hash, size_bytes, indexing_status, access_status"
                " FROM documents WHERE document_id = ?",
                (result.document_id,),
            ).fetchone()
            if doc_row is None:
                continue

            doc = DocumentRecord(
                document_id=doc_row[0],
                path=doc_row[1],
                content_hash=doc_row[2],
                size_bytes=doc_row[3],
                indexing_status=IndexingStatus(doc_row[4]),
            )

            citation = CitationRecord(
                document_id=result.document_id,
                chunk_id=result.chunk_id,
                label=f"[{i}]",
                state=CitationState.VALID,
            )
            citation = self._freshness.refresh_citation(citation, doc)

            text = chunk_row[0] if chunk_row[0] else result.snippet
            items.append(EvidenceItem(
                chunk_id=result.chunk_id,
                document_id=result.document_id,
                text=text,
                citation=citation,
                relevance_score=result.rrf_score,
                source_path=doc.path,
            ))

        return VerifiedEvidenceSet(
            items=tuple(items), query_fragments=tuple(fragments)
        )

    def _stub_build(
        self,
        results: Sequence[HybridSearchResult],
        fragments: Sequence[TypedQueryFragment],
    ) -> VerifiedEvidenceSet:
        """Phase 0 backward-compatible stub."""
        items: list[EvidenceItem] = []
        for i, result in enumerate(results, 1):
            citation = CitationRecord(
                document_id=result.document_id,
                chunk_id=result.chunk_id,
                label=f"[{i}]",
                state=CitationState.VALID,
            )
            items.append(EvidenceItem(
                chunk_id=result.chunk_id,
                document_id=result.document_id,
                text=result.snippet or f"Evidence from {result.document_id}",
                citation=citation,
                relevance_score=result.rrf_score,
            ))
        return VerifiedEvidenceSet(
            items=tuple(items), query_fragments=tuple(fragments)
        )
```

- [ ] **Step 3: Run tests, verify pass**
- [ ] **Step 4: Run full suite (all 168+ tests)**
- [ ] **Step 5: Commit**

```bash
git add src/jarvis/retrieval/evidence_builder.py tests/retrieval/test_evidence_builder.py
git commit -m "feat(retrieval): implement EvidenceBuilder with DB resolution and freshness checks"
```

---

### Task 6: Retrieval integration test — index → search → evidence

**Files:**
- Create: `tests/retrieval/test_retrieval_integration.py`

- [ ] **Step 1: Write integration test**

```python
# tests/retrieval/test_retrieval_integration.py
"""Integration test: full retrieval pipeline from indexed docs to evidence."""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Sequence

import pytest

from jarvis.app.bootstrap import init_database
from jarvis.app.config import JarvisConfig
from jarvis.contracts import CitationState
from jarvis.indexing.chunker import Chunker
from jarvis.indexing.index_pipeline import IndexPipeline
from jarvis.indexing.parsers import DocumentParser
from jarvis.indexing.tombstone import TombstoneManager
from jarvis.retrieval.evidence_builder import EvidenceBuilder
from jarvis.retrieval.fts_index import FTSIndex
from jarvis.retrieval.hybrid_search import HybridSearch
from jarvis.retrieval.query_decomposer import QueryDecomposer
from jarvis.retrieval.vector_index import VectorIndex


class FakeEmbeddingRuntime:
    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        return [[0.0] * 8 for _ in texts]


@pytest.fixture
def full_setup(tmp_path: Path) -> tuple[sqlite3.Connection, Path]:
    config = JarvisConfig(watched_folders=[tmp_path], data_dir=tmp_path / ".jarvis")
    db = init_database(config)
    pipeline = IndexPipeline(
        db=db,
        parser=DocumentParser(),
        chunker=Chunker(max_chunk_bytes=512, overlap_bytes=64),
        tombstone_manager=TombstoneManager(db=db),
        embedding_runtime=FakeEmbeddingRuntime(),
    )
    # Index diverse documents
    (tmp_path / "architecture.md").write_text(
        "# JARVIS Architecture\n\nThe system uses a monolith-first design.\n"
        "Protocol interfaces define all module boundaries."
    )
    (tmp_path / "korean_doc.md").write_text(
        "# 음성 인식 시스템\n\n로컬 환경에서 동작하는 음성 인식 엔진을 설계합니다.\n"
        "Whisper.cpp를 사용하여 한국어 음성을 텍스트로 변환합니다."
    )
    (tmp_path / "retrieval.py").write_text(
        '"""Retrieval pipeline for JARVIS."""\n\n'
        'def search(query: str) -> list:\n    """Search indexed documents."""\n    pass\n'
    )
    for f in tmp_path.glob("*"):
        if f.is_file():
            pipeline.index_file(f)
    return db, tmp_path


@pytest.mark.integration
class TestRetrievalRoundTrip:
    def test_english_query_finds_architecture(
        self, full_setup: tuple[sqlite3.Connection, Path]
    ) -> None:
        db, _ = full_setup
        decomposer = QueryDecomposer()
        fts = FTSIndex(db=db)
        vector = VectorIndex()  # stub — no real embeddings
        fusion = HybridSearch()
        evidence_builder = EvidenceBuilder(db=db)

        fragments = decomposer.decompose("architecture design")
        fts_hits = fts.search(fragments)
        vector_hits = vector.search(fragments)
        hybrid = fusion.fuse(fts_hits, vector_hits)
        evidence = evidence_builder.build(hybrid, fragments)

        assert not evidence.is_empty
        assert any("monolith" in item.text.lower() or "architecture" in item.text.lower()
                    for item in evidence.items)
        assert all(item.citation.state == CitationState.VALID for item in evidence.items)

    def test_korean_query_finds_korean_doc(
        self, full_setup: tuple[sqlite3.Connection, Path]
    ) -> None:
        db, _ = full_setup
        decomposer = QueryDecomposer()
        fts = FTSIndex(db=db)
        vector = VectorIndex()
        fusion = HybridSearch()
        evidence_builder = EvidenceBuilder(db=db)

        fragments = decomposer.decompose("음성 인식 시스템")
        fts_hits = fts.search(fragments)
        vector_hits = vector.search(fragments)
        hybrid = fusion.fuse(fts_hits, vector_hits)
        evidence = evidence_builder.build(hybrid, fragments)

        assert not evidence.is_empty
        assert any("음성" in item.text for item in evidence.items)

    def test_code_query_finds_python(
        self, full_setup: tuple[sqlite3.Connection, Path]
    ) -> None:
        db, _ = full_setup
        decomposer = QueryDecomposer()
        fts = FTSIndex(db=db)
        fusion = HybridSearch()
        evidence_builder = EvidenceBuilder(db=db)

        fragments = decomposer.decompose("search function")
        fts_hits = fts.search(fragments)
        hybrid = fusion.fuse(fts_hits, [])
        evidence = evidence_builder.build(hybrid, fragments)

        assert not evidence.is_empty

    def test_no_match_returns_empty_evidence(
        self, full_setup: tuple[sqlite3.Connection, Path]
    ) -> None:
        db, _ = full_setup
        decomposer = QueryDecomposer()
        fts = FTSIndex(db=db)
        fusion = HybridSearch()
        evidence_builder = EvidenceBuilder(db=db)

        fragments = decomposer.decompose("quantum entanglement teleportation")
        fts_hits = fts.search(fragments)
        hybrid = fusion.fuse(fts_hits, [])
        evidence = evidence_builder.build(hybrid, fragments)

        assert evidence.is_empty

    def test_evidence_has_source_paths(
        self, full_setup: tuple[sqlite3.Connection, Path]
    ) -> None:
        db, _ = full_setup
        fts = FTSIndex(db=db)
        evidence_builder = EvidenceBuilder(db=db)

        fragments = [__import__("jarvis.contracts", fromlist=["TypedQueryFragment"]).TypedQueryFragment(
            text="JARVIS", language="en", query_type="keyword"
        )]
        fts_hits = fts.search(fragments)
        fusion = HybridSearch()
        hybrid = fusion.fuse(fts_hits, [])
        evidence = evidence_builder.build(hybrid, fragments)

        for item in evidence.items:
            assert item.source_path  # non-empty path
            assert item.citation.label  # has label like [1]
```

- [ ] **Step 2: Run integration tests**
- [ ] **Step 3: Run complete test suite**
- [ ] **Step 4: Commit**

```bash
git add tests/retrieval/test_retrieval_integration.py
git commit -m "test(retrieval): add integration tests for full retrieval round-trip"
```
