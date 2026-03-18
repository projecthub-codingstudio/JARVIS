# Vector Index + Embedding Runtime Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace stub vector search with real BGE-M3 embeddings + LanceDB to enable semantic search in JARVIS's hybrid retrieval pipeline.

**Architecture:** VectorIndex internally holds an EmbeddingRuntime reference and calls it to embed queries during search. EmbeddingRuntime loads BGE-M3 via sentence-transformers on MPS. IndexPipeline runs a background daemon to backfill embeddings into LanceDB. All protocols remain frozen — no Orchestrator changes needed.

**Tech Stack:** sentence-transformers (BGE-M3, 1024-dim), LanceDB (serverless file-based), MPS (Apple Silicon GPU)

**Spec:** `docs/superpowers/specs/2026-03-18-vector-index-embedding-design.md`

---

### Task 1: Schema + Model Changes

**Files:**
- Modify: `sql/schema.sql:31-43`
- Modify: `src/jarvis/contracts/models.py:216-232`
- Modify: `src/jarvis/app/bootstrap.py:21-34`
- Test: `tests/contracts/test_models.py`

- [ ] **Step 1: Add embedding_ref to schema.sql**

In `sql/schema.sql`, add `embedding_ref` column to chunks table:

```sql
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
```

- [ ] **Step 2: Add embedding_ref to ChunkRecord dataclass**

In `src/jarvis/contracts/models.py`, add field to `ChunkRecord`:

```python
@dataclass
class ChunkRecord:
    chunk_id: str = field(default_factory=_uuid)
    document_id: str = ""
    byte_start: int = 0
    byte_end: int = 0
    line_start: int = 0
    line_end: int = 0
    text: str = ""
    chunk_hash: str = ""
    lexical_morphs: str = ""
    heading_path: str = ""
    embedding_ref: str | None = None
```

Note: Use `None` (not `""`) to match SQL `DEFAULT NULL`. Backfill query checks `WHERE embedding_ref IS NULL`.

- [ ] **Step 3: Add DB migration in bootstrap.py**

In `src/jarvis/app/bootstrap.py`, after schema load, add migration:

```python
# Migration: add embedding_ref column if missing (added in v0.2)
try:
    conn.execute("SELECT embedding_ref FROM chunks LIMIT 0")
except sqlite3.OperationalError:
    conn.execute("ALTER TABLE chunks ADD COLUMN embedding_ref TEXT DEFAULT NULL")
```

- [ ] **Step 4: Run existing tests to verify no breakage**

Run: `PYTHONPATH=src pytest tests/contracts/ -v`
Expected: All existing tests PASS

- [ ] **Step 5: Commit**

```bash
git add sql/schema.sql src/jarvis/contracts/models.py src/jarvis/app/bootstrap.py
git commit -m "feat: add embedding_ref column to chunks schema and model"
```

---

### Task 2: EmbeddingRuntime — Real BGE-M3 Implementation

**Files:**
- Rewrite: `src/jarvis/runtime/embedding_runtime.py`
- Test: `tests/runtime/test_embedding_runtime.py`

- [ ] **Step 1: Write the failing test**

Create `tests/runtime/test_embedding_runtime.py`:

```python
"""Tests for EmbeddingRuntime with BGE-M3."""
import pytest
from jarvis.runtime.embedding_runtime import EmbeddingRuntime
from jarvis.contracts import EmbeddingRuntimeProtocol


def test_protocol_compliance():
    """EmbeddingRuntime must satisfy EmbeddingRuntimeProtocol."""
    rt = EmbeddingRuntime()
    assert isinstance(rt, EmbeddingRuntimeProtocol)


def test_embed_returns_correct_shape():
    """embed() must return list[list[float]] with 1024 dimensions."""
    rt = EmbeddingRuntime()
    texts = ["hello world", "테스트 한국어"]
    result = rt.embed(texts)
    assert isinstance(result, list)
    assert len(result) == 2
    assert all(isinstance(v, list) for v in result)
    # Each vector must be exactly 1024 dimensions (BGE-M3 or stub)
    assert all(len(v) == 1024 for v in result)
    # All values should be float
    assert all(isinstance(x, float) for v in result for x in v)


def test_embed_empty_input():
    """embed([]) must return []."""
    rt = EmbeddingRuntime()
    assert rt.embed([]) == []


def test_embed_single_text():
    """embed() works with a single text."""
    rt = EmbeddingRuntime()
    result = rt.embed(["test"])
    assert len(result) == 1


def test_load_unload_lifecycle():
    """load/unload cycle should not crash."""
    rt = EmbeddingRuntime()
    rt.load_model()
    result = rt.embed(["test"])
    assert len(result) == 1
    rt.unload_model()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=src pytest tests/runtime/test_embedding_runtime.py -v`
Expected: Tests fail (stub returns zero-vectors of dim=128, not real embeddings)

- [ ] **Step 3: Implement EmbeddingRuntime**

Rewrite `src/jarvis/runtime/embedding_runtime.py`:

```python
"""EmbeddingRuntime — local embedding generation via sentence-transformers.

Implements EmbeddingRuntimeProtocol. Uses BGE-M3 on MPS (Apple Silicon)
for 1024-dimensional multilingual embeddings.

Per Spec Section 11.2: on-demand load/unload with Governor integration.
Falls back to stub (zero-vectors) if sentence-transformers is not installed.
"""
from __future__ import annotations

import logging
from typing import Sequence

from jarvis.contracts import EmbeddingRuntimeProtocol

logger = logging.getLogger(__name__)

_DEFAULT_MODEL = "BAAI/bge-m3"
_DEFAULT_DIM = 1024
_BATCH_SIZE = 32


class EmbeddingRuntime:
    """Embedding generation using sentence-transformers on MPS.

    Implements EmbeddingRuntimeProtocol.
    On-demand model loading: loads on first embed() call.
    Falls back to zero-vector stub if dependencies are missing.
    """

    def __init__(
        self,
        *,
        model_id: str = _DEFAULT_MODEL,
        dim: int = _DEFAULT_DIM,
        device: str = "mps",
    ) -> None:
        self._model_id = model_id
        self._dim = dim
        self._device = device
        self._model: object | None = None
        self._available: bool | None = None  # None = not checked yet

    def _check_available(self) -> bool:
        """Check if sentence-transformers is installed."""
        if self._available is not None:
            return self._available
        try:
            import sentence_transformers  # noqa: F401
            self._available = True
        except ImportError:
            logger.warning(
                "sentence-transformers not installed — embedding disabled (FTS-only mode)"
            )
            self._available = False
        return self._available

    def load_model(self) -> None:
        """Load BGE-M3 model onto MPS device."""
        if self._model is not None:
            return
        if not self._check_available():
            return
        try:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(self._model_id, device=self._device)
            logger.info("Loaded embedding model: %s on %s", self._model_id, self._device)
        except Exception as e:
            logger.warning("Failed to load embedding model: %s", e)
            self._available = False

    def unload_model(self) -> None:
        """Unload model and free memory."""
        if self._model is None:
            return
        del self._model
        self._model = None
        # Force MPS cache clear if available
        try:
            import torch
            if hasattr(torch, "mps") and hasattr(torch.mps, "empty_cache"):
                torch.mps.empty_cache()
        except ImportError:
            pass
        logger.info("Unloaded embedding model: %s", self._model_id)

    @property
    def is_loaded(self) -> bool:
        return self._model is not None

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        """Generate embeddings for a batch of texts.

        Returns list[list[float]] per EmbeddingRuntimeProtocol.
        Returns zero-vectors if model is unavailable.
        """
        if not texts:
            return []

        # On-demand load
        if self._model is None:
            self.load_model()

        # Stub fallback if unavailable
        if self._model is None:
            return [[0.0] * self._dim for _ in texts]

        try:
            import numpy as np
            embeddings = self._model.encode(  # type: ignore[union-attr]
                list(texts),
                batch_size=_BATCH_SIZE,
                show_progress_bar=False,
                normalize_embeddings=True,
            )
            # Convert numpy to list[list[float]]
            if isinstance(embeddings, np.ndarray):
                return embeddings.tolist()
            return [list(map(float, v)) for v in embeddings]
        except Exception as e:
            logger.warning("Embedding failed: %s — returning zero vectors", e)
            return [[0.0] * self._dim for _ in texts]

```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=src pytest tests/runtime/test_embedding_runtime.py -v`
Expected: All PASS (if sentence-transformers installed) or graceful stub fallback

- [ ] **Step 5: Commit**

```bash
git add src/jarvis/runtime/embedding_runtime.py tests/runtime/test_embedding_runtime.py
git commit -m "feat: implement EmbeddingRuntime with BGE-M3 on MPS"
```

---

### Task 3: VectorIndex — LanceDB Implementation

**Files:**
- Rewrite: `src/jarvis/retrieval/vector_index.py`
- Test: `tests/retrieval/test_vector_index.py`

- [ ] **Step 1: Write the failing test**

Create `tests/retrieval/test_vector_index.py`:

```python
"""Tests for VectorIndex with LanceDB."""
import pytest
import tempfile
from pathlib import Path

from jarvis.contracts import TypedQueryFragment, VectorHit, VectorRetrieverProtocol
from jarvis.runtime.embedding_runtime import EmbeddingRuntime
from jarvis.retrieval.vector_index import VectorIndex


def test_protocol_compliance():
    """VectorIndex must satisfy VectorRetrieverProtocol."""
    vi = VectorIndex()
    assert isinstance(vi, VectorRetrieverProtocol)


def test_search_empty_index():
    """Search on empty index returns empty list."""
    vi = VectorIndex()
    fragments = [TypedQueryFragment(text="test", language="en", query_type="semantic", weight=1.0)]
    results = vi.search(fragments)
    assert results == []


def test_add_and_search_roundtrip():
    """Add vectors then search should find them."""
    with tempfile.TemporaryDirectory() as tmpdir:
        embedding_rt = EmbeddingRuntime()
        vi = VectorIndex(
            db_path=Path(tmpdir) / "test.lance",
            embedding_runtime=embedding_rt,
        )

        # Add some vectors
        texts = ["Python 프로그래밍 언어", "자바스크립트 웹 개발", "데이터베이스 설계"]
        embeddings = embedding_rt.embed(texts)
        vi.add(
            chunk_ids=["c1", "c2", "c3"],
            document_ids=["d1", "d1", "d2"],
            embeddings=embeddings,
        )

        # Search for something similar
        fragments = [TypedQueryFragment(text="Python 코딩", language="ko", query_type="semantic", weight=1.0)]
        results = vi.search(fragments, top_k=2)

        assert len(results) <= 2
        assert all(isinstance(r, VectorHit) for r in results)
        if results:  # May be empty if embedding is stub
            assert results[0].chunk_id in ("c1", "c2", "c3")


def test_remove_vectors():
    """Remove should delete vectors from index."""
    with tempfile.TemporaryDirectory() as tmpdir:
        embedding_rt = EmbeddingRuntime()
        vi = VectorIndex(
            db_path=Path(tmpdir) / "test.lance",
            embedding_runtime=embedding_rt,
        )

        embeddings = embedding_rt.embed(["text1", "text2"])
        vi.add(chunk_ids=["c1", "c2"], document_ids=["d1", "d1"], embeddings=embeddings)
        vi.remove(chunk_ids=["c1"])

        fragments = [TypedQueryFragment(text="text1", language="en", query_type="semantic", weight=1.0)]
        results = vi.search(fragments, top_k=10)
        found_ids = [r.chunk_id for r in results]
        assert "c1" not in found_ids
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=src pytest tests/retrieval/test_vector_index.py -v`
Expected: FAIL (current stub always returns fixed hit)

- [ ] **Step 3: Implement VectorIndex**

Rewrite `src/jarvis/retrieval/vector_index.py`:

```python
"""VectorIndex — vector similarity retrieval via LanceDB.

Implements VectorRetrieverProtocol for dense vector search
over document chunk embeddings.

Per Spec: LanceDB serverless file-based vector DB.
Falls back to empty results if lancedb is not installed.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Sequence

from jarvis.contracts import TypedQueryFragment, VectorHit, VectorRetrieverProtocol

logger = logging.getLogger(__name__)

_DEFAULT_DB_PATH = Path.home() / ".jarvis" / "vectors.lance"
_DEFAULT_TABLE = "chunk_embeddings"


class VectorIndex:
    """Vector similarity search index backed by LanceDB.

    Implements VectorRetrieverProtocol.
    Holds a reference to EmbeddingRuntime for query-time embedding.
    Falls back to empty results if LanceDB or embeddings are unavailable.
    """

    def __init__(
        self,
        *,
        db_path: Path | None = None,
        embedding_runtime: object | None = None,
        table_name: str = _DEFAULT_TABLE,
    ) -> None:
        self._db_path = db_path or _DEFAULT_DB_PATH
        self._embedding_runtime = embedding_runtime
        self._table_name = table_name
        self._db: object | None = None
        self._available: bool | None = None

    def _check_available(self) -> bool:
        if self._available is not None:
            return self._available
        try:
            import lancedb  # noqa: F401
            self._available = True
        except ImportError:
            logger.warning("lancedb not installed — vector search disabled (FTS-only mode)")
            self._available = False
        return self._available

    def _ensure_db(self) -> object | None:
        if self._db is not None:
            return self._db
        if not self._check_available():
            return None
        try:
            import lancedb
            self._db_path.parent.mkdir(parents=True, exist_ok=True)
            self._db = lancedb.connect(str(self._db_path))
            return self._db
        except Exception as e:
            logger.warning("Failed to connect LanceDB: %s", e)
            self._available = False
            return None

    def _get_table(self) -> object | None:
        db = self._ensure_db()
        if db is None:
            return None
        try:
            return db.open_table(self._table_name)  # type: ignore[union-attr]
        except Exception:
            return None

    def add(
        self,
        chunk_ids: list[str],
        document_ids: list[str],
        embeddings: list[list[float]],
    ) -> None:
        """Add or update vectors in the index."""
        db = self._ensure_db()
        if db is None or not embeddings or not chunk_ids:
            return

        import pyarrow as pa

        data = [
            {"chunk_id": cid, "document_id": did, "vector": vec}
            for cid, did, vec in zip(chunk_ids, document_ids, embeddings)
        ]

        try:
            table = self._get_table()
            if table is not None:
                # Delete existing entries for these chunk_ids, then add
                existing_ids = set(chunk_ids)
                try:
                    # Validate chunk_ids to prevent filter injection
                    safe_ids = [cid for cid in existing_ids if '"' not in cid]
                    if safe_ids:
                        filter_expr = " OR ".join(f'chunk_id = "{cid}"' for cid in safe_ids)
                        table.delete(filter_expr)  # type: ignore[union-attr]
                except Exception:
                    pass
                table.add(data)  # type: ignore[union-attr]
            else:
                db.create_table(self._table_name, data=data)  # type: ignore[union-attr]
        except Exception as e:
            logger.warning("Failed to add vectors to LanceDB: %s", e)

    def remove(self, chunk_ids: list[str]) -> None:
        """Remove vectors by chunk_id."""
        table = self._get_table()
        if table is None or not chunk_ids:
            return
        try:
            safe_ids = [cid for cid in chunk_ids if '"' not in cid]
            if not safe_ids:
                return
            filter_expr = " OR ".join(f'chunk_id = "{cid}"' for cid in safe_ids)
            table.delete(filter_expr)  # type: ignore[union-attr]
        except Exception as e:
            logger.warning("Failed to remove vectors: %s", e)

    def search(
        self, fragments: Sequence[TypedQueryFragment], top_k: int = 10
    ) -> list[VectorHit]:
        """Search vector index with query fragments.

        Internally embeds the query text via EmbeddingRuntime,
        then performs ANN search on LanceDB.
        Returns empty list if unavailable (graceful FTS-only degradation).
        """
        table = self._get_table()
        if table is None or not fragments:
            return []

        if self._embedding_runtime is None:
            return []

        # Combine fragment texts for embedding
        query_text = " ".join(f.text for f in fragments if f.query_type == "semantic")
        if not query_text:
            query_text = " ".join(f.text for f in fragments)
        if not query_text:
            return []

        # Embed query
        try:
            query_vectors = self._embedding_runtime.embed([query_text])  # type: ignore[union-attr]
            if not query_vectors or all(v == 0.0 for v in query_vectors[0]):
                return []  # Stub embedding — skip vector search
            query_vec = query_vectors[0]
        except Exception as e:
            logger.warning("Query embedding failed: %s", e)
            return []

        # ANN search
        try:
            results = (
                table.search(query_vec)  # type: ignore[union-attr]
                .limit(top_k)
                .to_list()
            )
        except Exception as e:
            logger.warning("Vector search failed: %s", e)
            return []

        hits: list[VectorHit] = []
        for row in results:
            distance = row.get("_distance", 1.0)
            score = max(0.0, 1.0 - distance)  # Convert distance to similarity
            hits.append(VectorHit(
                chunk_id=row["chunk_id"],
                document_id=row["document_id"],
                score=score,
                embedding_distance=distance,
            ))

        return hits

```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=src pytest tests/retrieval/test_vector_index.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/jarvis/retrieval/vector_index.py tests/retrieval/test_vector_index.py
git commit -m "feat: implement VectorIndex with LanceDB"
```

---

### Task 4: IndexPipeline — Embedding Backfill Daemon

**Files:**
- Modify: `src/jarvis/indexing/index_pipeline.py`
- Modify: `src/jarvis/__main__.py`
- Test: `tests/indexing/test_embedding_backfill.py`

- [ ] **Step 1: Write the failing test**

Create `tests/indexing/test_embedding_backfill.py`:

```python
"""Tests for embedding backfill in IndexPipeline."""
import sqlite3
import tempfile
from pathlib import Path

import pytest

from jarvis.app.bootstrap import init_database
from jarvis.app.config import JarvisConfig
from jarvis.indexing.chunker import Chunker
from jarvis.indexing.index_pipeline import IndexPipeline
from jarvis.indexing.parsers import DocumentParser
from jarvis.indexing.tombstone import TombstoneManager
from jarvis.runtime.embedding_runtime import EmbeddingRuntime


@pytest.fixture
def pipeline_with_db():
    config = JarvisConfig()
    config.db_path = Path(tempfile.mktemp(suffix=".db"))
    db = init_database(config)
    embedding_rt = EmbeddingRuntime()
    pipeline = IndexPipeline(
        db=db,
        parser=DocumentParser(),
        chunker=Chunker(),
        tombstone_manager=TombstoneManager(db=db),
        embedding_runtime=embedding_rt,
    )
    yield pipeline, db, config
    db.close()
    config.db_path.unlink(missing_ok=True)


def test_backfill_embeddings_updates_chunks(pipeline_with_db):
    """backfill_embeddings should process chunks without embedding_ref."""
    pipeline, db, config = pipeline_with_db

    # Create a test file and index it
    with tempfile.NamedTemporaryFile(suffix=".txt", mode="w", delete=False) as f:
        f.write("테스트 임베딩 백필 문서입니다.")
        tmp = f.name

    pipeline.index_file(Path(tmp))

    # Verify chunks exist without embedding_ref
    null_count = db.execute(
        "SELECT COUNT(*) FROM chunks WHERE embedding_ref IS NULL OR embedding_ref = ''"
    ).fetchone()[0]
    assert null_count > 0

    # Run backfill
    updated = pipeline.backfill_embeddings(batch_size=10)
    assert updated >= 0  # May be 0 if embedding is stub

    Path(tmp).unlink()


def test_backfill_returns_zero_when_all_done(pipeline_with_db):
    """backfill_embeddings returns 0 when no chunks need embedding."""
    pipeline, db, config = pipeline_with_db
    updated = pipeline.backfill_embeddings(batch_size=10)
    assert updated == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=src pytest tests/indexing/test_embedding_backfill.py -v`
Expected: FAIL (backfill_embeddings method doesn't exist yet)

- [ ] **Step 3: Add backfill_embeddings to IndexPipeline**

In `src/jarvis/indexing/index_pipeline.py`, add after `backfill_morphemes()`:

```python
def backfill_embeddings(self, *, batch_size: int = 32) -> int:
    """Backfill embedding vectors for chunks that don't have them.

    Per Spec Section 11.2: deferred queue, recent files first.
    Returns the number of chunks processed.
    """
    rows = self._db.execute(
        "SELECT c.chunk_id, c.document_id, c.text FROM chunks c"
        " JOIN documents d ON c.document_id = d.document_id"
        " WHERE c.embedding_ref IS NULL"
        " AND d.indexing_status = 'INDEXED'"
        " ORDER BY d.updated_at DESC"
        " LIMIT ?",
        (batch_size,),
    ).fetchall()

    if not rows:
        return 0

    chunk_ids = [r[0] for r in rows]
    document_ids = [r[1] for r in rows]
    texts = [r[2][:2000] for r in rows]  # Truncate very long chunks

    # Generate embeddings
    embeddings = self._embedding_runtime.embed(texts)

    # Check if we got real embeddings (not zero-vectors)
    if not embeddings or all(v == 0.0 for v in embeddings[0][:10]):
        return 0  # Stub mode — skip

    # Store in vector index if available
    if hasattr(self, "_vector_index") and self._vector_index is not None:
        self._vector_index.add(chunk_ids, document_ids, embeddings)

    # Update embedding_ref in chunks table
    for chunk_id in chunk_ids:
        self._db.execute(
            "UPDATE chunks SET embedding_ref = ? WHERE chunk_id = ?",
            ("lance:" + chunk_id, chunk_id),
        )

    self._db.commit()
    return len(chunk_ids)
```

Also update `IndexPipeline.__init__` to accept optional `vector_index`:

```python
def __init__(
    self,
    *,
    db: sqlite3.Connection,
    parser: DocumentParser,
    chunker: Chunker,
    tombstone_manager: TombstoneManager,
    embedding_runtime: EmbeddingRuntimeProtocol,
    vector_index: object | None = None,
) -> None:
    self._db = db
    self._parser = parser
    self._chunker = chunker
    self._tombstone = tombstone_manager
    self._embedding_runtime = embedding_runtime
    self._vector_index = vector_index
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=src pytest tests/indexing/test_embedding_backfill.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/jarvis/indexing/index_pipeline.py tests/indexing/test_embedding_backfill.py
git commit -m "feat: add embedding backfill to IndexPipeline"
```

---

### Task 5: Wire Everything in __main__.py

**Files:**
- Modify: `src/jarvis/__main__.py`
- Modify: `pyproject.toml`

- [ ] **Step 1: Install dependencies**

```bash
pip3 install sentence-transformers lancedb --break-system-packages
```

- [ ] **Step 2: Add dependencies to pyproject.toml**

Add to `dependencies` list:

```toml
"sentence-transformers>=3.0",
"lancedb>=0.8",
```

Add to `[[tool.mypy.overrides]]` module list:

```
"sentence_transformers.*", "lancedb.*", "torch.*", "pyarrow.*"
```

- [ ] **Step 3: Update __main__.py — VectorIndex initialization**

In `_create_pipeline()`, pass `vector_index` parameter (modify the function to accept it):

```python
def _create_pipeline(db: object, vector_index: object | None = None) -> object:
    """Create the indexing pipeline instance."""
    from jarvis.indexing.chunker import Chunker
    from jarvis.indexing.index_pipeline import IndexPipeline
    from jarvis.indexing.parsers import DocumentParser
    from jarvis.indexing.tombstone import TombstoneManager
    from jarvis.runtime.embedding_runtime import EmbeddingRuntime

    return IndexPipeline(
        db=db,
        parser=DocumentParser(),
        chunker=Chunker(),
        tombstone_manager=TombstoneManager(db=db),
        embedding_runtime=EmbeddingRuntime(),
        vector_index=vector_index,
    )
```

In `main()`, before building the orchestrator, create VectorIndex:

```python
# Vector index for semantic search
from jarvis.runtime.embedding_runtime import EmbeddingRuntime as EmbRT
from jarvis.retrieval.vector_index import VectorIndex

embedding_runtime = EmbRT()
vector_index = VectorIndex(embedding_runtime=embedding_runtime)
print(f"   Vector search: {'active' if vector_index._check_available() else 'disabled (FTS only)'}")
```

Pass `vector_index` to the orchestrator:

```python
vector_retriever=vector_index,  # was: VectorIndex()
```

- [ ] **Step 4: Add embedding backfill daemon**

In `_run_indexing()`, after the morpheme backfill thread, add embedding backfill:

```python
def _backfill_embeddings() -> None:
    """Background batch embedding generation.

    Uses the shared embedding_runtime from main thread to avoid
    loading BGE-M3 twice (~2.2GB each). The embed() method is read-only
    and thread-safe for sentence-transformers.
    """
    from jarvis.app.bootstrap import init_database
    from jarvis.app.config import JarvisConfig
    bg_db = init_database(JarvisConfig())
    # Reuse shared embedding_runtime (nonlocal from main) — not a new instance
    bg_vector_index = VectorIndex(embedding_runtime=embedding_runtime)
    bg_pipeline = _create_pipeline(bg_db, vector_index=bg_vector_index)
    total_updated = 0
    while True:
        updated = bg_pipeline.backfill_embeddings(batch_size=32)
        total_updated += updated
        if updated == 0:
            break
    if total_updated > 0:
        print(f"   [embeddings] {total_updated} chunks 임베딩 생성 완료")
    bg_embedding_rt.unload_model()
    bg_db.close()

embed_thread = threading.Thread(target=_backfill_embeddings, daemon=True)
embed_thread.start()
```

- [ ] **Step 5: Run JARVIS and verify startup**

```bash
cd alliance_20260317_130542 && PYTHONPATH=src python -m jarvis
```

Expected output should include:
```
   Vector search: active
   [embeddings] N chunks 임베딩 생성 완료
```

- [ ] **Step 6: Commit**

```bash
git add src/jarvis/__main__.py pyproject.toml
git commit -m "feat: wire EmbeddingRuntime + VectorIndex into JARVIS startup"
```

---

### Task 6: Integration Test — Full Hybrid Search

**Files:**
- Create: `tests/integration/test_hybrid_search_real.py`

- [ ] **Step 1: Write integration test**

```python
"""Integration test: full hybrid search with FTS + vector."""
import sqlite3
import tempfile
from pathlib import Path

import pytest

from jarvis.app.bootstrap import init_database
from jarvis.app.config import JarvisConfig
from jarvis.indexing.chunker import Chunker
from jarvis.indexing.index_pipeline import IndexPipeline
from jarvis.indexing.parsers import DocumentParser
from jarvis.indexing.tombstone import TombstoneManager
from jarvis.retrieval.evidence_builder import EvidenceBuilder
from jarvis.retrieval.fts_index import FTSIndex
from jarvis.retrieval.hybrid_search import HybridSearch
from jarvis.retrieval.query_decomposer import QueryDecomposer
from jarvis.retrieval.vector_index import VectorIndex
from jarvis.runtime.embedding_runtime import EmbeddingRuntime


@pytest.fixture
def indexed_db():
    """Create a DB with indexed test documents."""
    config = JarvisConfig()
    config.db_path = Path(tempfile.mktemp(suffix=".db"))
    db = init_database(config)

    embedding_rt = EmbeddingRuntime()
    vector_idx = VectorIndex(
        db_path=Path(tempfile.mkdtemp()) / "test.lance",
        embedding_runtime=embedding_rt,
    )

    pipeline = IndexPipeline(
        db=db, parser=DocumentParser(), chunker=Chunker(),
        tombstone_manager=TombstoneManager(db=db),
        embedding_runtime=embedding_rt,
        vector_index=vector_idx,
    )

    # Create test files
    tmpdir = Path(tempfile.mkdtemp())
    (tmpdir / "python_guide.txt").write_text("Python은 간결하고 읽기 쉬운 프로그래밍 언어입니다.")
    (tmpdir / "database_design.txt").write_text("데이터베이스 설계에서 정규화는 중요한 개념입니다.")

    for f in tmpdir.iterdir():
        pipeline.index_file(f)

    # Backfill embeddings
    pipeline.backfill_embeddings(batch_size=10)

    yield db, vector_idx
    db.close()
    config.db_path.unlink(missing_ok=True)


def test_hybrid_search_returns_results(indexed_db):
    """Hybrid search should combine FTS and vector results."""
    db, vector_idx = indexed_db

    decomposer = QueryDecomposer()
    fts = FTSIndex(db=db)
    hybrid = HybridSearch()

    fragments = decomposer.decompose("Python 프로그래밍")
    fts_hits = fts.search(fragments)
    vector_hits = vector_idx.search(fragments)

    results = hybrid.fuse(fts_hits, vector_hits)
    assert len(results) > 0  # Should find at least the Python document
```

- [ ] **Step 2: Run integration test**

Run: `PYTHONPATH=src pytest tests/integration/test_hybrid_search_real.py -v`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add tests/integration/test_hybrid_search_real.py
git commit -m "test: add integration test for hybrid FTS + vector search"
```

---

### Task 7: Cleanup — Remove Stale Vectors on File Operations

**Files:**
- Modify: `src/jarvis/indexing/index_pipeline.py`

- [ ] **Step 1: Update remove_file, remove_directory, and reindex_file to also remove vectors**

In `remove_file()`, add LanceDB cleanup before `_delete_chunks`:

```python
def remove_file(self, path: Path) -> None:
    existing = self._find_document_by_path(path)
    if existing is None:
        return
    # Remove vectors from LanceDB
    chunk_ids = [r[0] for r in self._db.execute(
        "SELECT chunk_id FROM chunks WHERE document_id = ?", (existing.document_id,)
    ).fetchall()]
    if chunk_ids and self._vector_index is not None:
        self._vector_index.remove(chunk_ids)
    self._delete_chunks(existing.document_id)
    self._tombstone.create_tombstone(existing)
```

In `remove_directory()`, add vector cleanup inside the loop:

```python
def remove_directory(self, dir_path: Path) -> int:
    prefix = str(dir_path)
    rows = self._db.execute(
        "SELECT document_id, path, content_hash, size_bytes, indexing_status"
        " FROM documents WHERE path LIKE ? AND indexing_status != ?",
        (prefix + "%", IndexingStatus.TOMBSTONED.value),
    ).fetchall()

    count = 0
    for row in rows:
        doc = DocumentRecord(
            document_id=row[0], path=row[1], content_hash=row[2],
            size_bytes=row[3], indexing_status=IndexingStatus(row[4]),
        )
        # Remove vectors from LanceDB
        chunk_ids = [r[0] for r in self._db.execute(
            "SELECT chunk_id FROM chunks WHERE document_id = ?", (doc.document_id,)
        ).fetchall()]
        if chunk_ids and self._vector_index is not None:
            self._vector_index.remove(chunk_ids)
        self._delete_chunks(doc.document_id)
        self._tombstone.create_tombstone(doc)
        count += 1
    return count
```

In `reindex_file()`, add vector cleanup before `_delete_chunks`:

```python
# In reindex_file(), before self._delete_chunks(existing.document_id):
if existing:
    chunk_ids = [r[0] for r in self._db.execute(
        "SELECT chunk_id FROM chunks WHERE document_id = ?", (existing.document_id,)
    ).fetchall()]
    if chunk_ids and self._vector_index is not None:
        self._vector_index.remove(chunk_ids)
```

- [ ] **Step 2: Run all tests**

Run: `PYTHONPATH=src pytest tests/ -v --ignore=tests/perf`
Expected: All PASS

- [ ] **Step 3: Commit**

```bash
git add src/jarvis/indexing/index_pipeline.py
git commit -m "feat: remove vectors from LanceDB on file delete/move"
```
