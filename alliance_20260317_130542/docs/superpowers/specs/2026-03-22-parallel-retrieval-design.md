# Parallel Retrieval Search Design

**Date**: 2026-03-22
**Status**: Approved
**Scope**: FTS5 + Vector search parallelization, RRF fusion optimization

## Problem

FTS5 and Vector search run sequentially in `orchestrator.py:222-223`. A parallel branch exists (lines 215-220) but is dead code — the `can_parallelize` guard checks `_db is None`, which is always `False` in production since `FTSIndex` holds a live `sqlite3.Connection`.

## Solution: ThreadPoolExecutor + check_same_thread=False

### Changes

1. **`bootstrap.py`**: Add `check_same_thread=False` to `sqlite3.connect()` call. WAL mode is already enabled (line 27), which supports concurrent reads.

2. **`orchestrator.py`**: Remove the broken `can_parallelize` guard. Always use `ThreadPoolExecutor(max_workers=2)` for FTS + Vector search. Add metrics recording for parallel retrieval latency.

3. **`hybrid_search.py`**: Replace O(n×m) linear scan for vector rank lookup with O(1) dict lookup. Pre-build `{chunk_id: rank}` map from vector_hits before the FTS pass.

4. **`benchmark.py`**: Update to use parallel search pattern matching production code.

### Thread Safety Analysis

| Component | Thread-safe? | Notes |
|-----------|-------------|-------|
| `FTSIndex.search` | Yes with WAL + `check_same_thread=False` | Read-only SQLite, WAL allows concurrent reads |
| `VectorIndex.search` | Yes | No shared mutable state; LanceDB handles its own concurrency |
| `KiwiTokenizer` | Yes | Singleton but stateless read operations |
| `EmbeddingRuntime.embed` | Yes | sentence-transformers is thread-safe for inference |
| `HybridSearch.fuse` | Yes | Stateless, no instance mutation |

### Expected Impact

- FTS search: ~50-200ms (Korean morpheme expansion + SQLite)
- Vector search: ~100-500ms (embedding + ANN)
- Sequential total: ~150-700ms
- Parallel total: ~max(FTS, Vector) = ~100-500ms
- **Expected improvement: ~30-50% reduction in retrieval latency**

### Risk Mitigation

- WAL mode already active — no migration needed
- `check_same_thread=False` is safe for read-only concurrent access
- SQLite lock retry logic in FTSIndex already handles contention
- Fallback: if ThreadPoolExecutor raises, catch and fall back to sequential
