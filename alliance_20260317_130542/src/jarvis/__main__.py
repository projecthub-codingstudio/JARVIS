"""Entry point for `python -m jarvis`.

Implements the startup sequence per Implementation Spec Section 1.5:
  python -m jarvis.app.cli chat

Backend selection per Spec Section 1.1:
  - Default inference backend: MLX
  - Compatibility backend: llama.cpp (Ollama)
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from jarvis.app.bootstrap import bootstrap
from jarvis.cli.repl import JarvisREPL
from jarvis.contracts import RuntimeDecision
from jarvis.core.governor import Governor, GovernorStub
from jarvis.core.orchestrator import Orchestrator
from jarvis.core.tool_registry import ToolRegistry
from jarvis.memory.conversation_store import ConversationStore
from jarvis.memory.task_log import TaskLogStore
from jarvis.retrieval.evidence_builder import EvidenceBuilder
from jarvis.retrieval.fts_index import FTSIndex
from jarvis.retrieval.hybrid_search import HybridSearch
from jarvis.retrieval.query_decomposer import QueryDecomposer
from jarvis.retrieval.vector_index import VectorIndex
from jarvis.runtime.mlx_runtime import MLXRuntime

logger = logging.getLogger(__name__)

# Default knowledge base path
_DEFAULT_KB_PATH = Path("/Users/codingstudio/__PROJECTHUB__/JARVIS/knowledge_base")

_SUPPORTED_EXTENSIONS: frozenset[str] = frozenset({
    ".md", ".markdown", ".txt", ".rst", ".cfg", ".toml", ".ini",
    ".py", ".ts", ".tsx", ".js", ".jsx", ".yaml", ".yml", ".json",
    ".pdf", ".docx", ".xlsx", ".hwpx", ".hwp",
})


def _has_indexed_data(db: object) -> bool:
    """Check if the database has any indexed documents."""
    try:
        row = db.execute("SELECT COUNT(*) FROM chunks").fetchone()  # type: ignore[union-attr]
        return row[0] > 0  # type: ignore[index]
    except Exception:
        return False


def _create_pipeline(db: object) -> object:
    """Create the indexing pipeline instance."""
    from jarvis.indexing.chunker import Chunker
    from jarvis.indexing.index_pipeline import IndexPipeline
    from jarvis.indexing.parsers import DocumentParser
    from jarvis.indexing.tombstone import TombstoneManager
    from jarvis.runtime.embedding_runtime import EmbeddingRuntime

    return IndexPipeline(
        db=db,  # type: ignore[arg-type]
        parser=DocumentParser(),
        chunker=Chunker(),
        tombstone_manager=TombstoneManager(db=db),  # type: ignore[arg-type]
        embedding_runtime=EmbeddingRuntime(),
    )


def _run_indexing(db: object, kb_path: Path) -> tuple[int, object]:
    """Index files in knowledge_base directory. Returns (chunk_count, pipeline).

    Per Spec Task 1.1: metadata first (synchronous), morphemes later
    (background batch via deferred queue).
    """
    pipeline = _create_pipeline(db)

    files = [f for f in kb_path.rglob("*")
             if f.is_file() and f.suffix.lower() in _SUPPORTED_EXTENSIONS]

    for f in files:
        try:
            pipeline.index_file(f)  # type: ignore[union-attr]
        except Exception as e:
            logger.warning("Index failed for %s: %s", f.name, e)

    total = db.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]  # type: ignore[union-attr]

    # Start background morpheme backfill (Spec Task 1.1: deferred queue)
    import threading

    def _backfill_morphemes() -> None:
        """Background batch morpheme analysis."""
        from jarvis.app.bootstrap import init_database
        from jarvis.app.config import JarvisConfig
        bg_db = init_database(JarvisConfig())
        bg_pipeline = _create_pipeline(bg_db)
        total_updated = 0
        while True:
            updated = bg_pipeline.backfill_morphemes(batch_size=50)  # type: ignore[union-attr]
            total_updated += updated
            if updated == 0:
                break
        if total_updated > 0:
            print(f"   [morphemes] {total_updated} chunks 형태소 분석 완료")
        bg_db.close()  # type: ignore[union-attr]

    thread = threading.Thread(target=_backfill_morphemes, daemon=True)
    thread.start()

    return total, pipeline


def _start_file_watcher(db: object, kb_path: Path) -> object:
    """Start FileWatcher for real-time indexing per Spec Task 1.2.

    Watches knowledge_base/ for file changes (create/modify/delete)
    and feeds them into the IndexPipeline.

    Uses a dedicated SQLite connection for the watcher thread
    since SQLite connections cannot cross thread boundaries.
    """
    import sqlite3
    import threading

    from jarvis.app.config import JarvisConfig
    from jarvis.app.bootstrap import init_database
    from jarvis.indexing.file_watcher import FileWatcher

    # Create a dedicated DB connection for the watcher thread
    config = JarvisConfig()
    watcher_db: sqlite3.Connection | None = None
    watcher_pipeline: object = None
    db_lock = threading.Lock()

    def _ensure_thread_db() -> None:
        nonlocal watcher_db, watcher_pipeline
        if watcher_db is None:
            watcher_db = init_database(config)
            watcher_pipeline = _create_pipeline(watcher_db)

    def on_change(path: Path, event_type: str) -> None:
        # Skip unsupported extensions and temp files
        if path.suffix.lower() not in _SUPPORTED_EXTENSIONS:
            return
        if path.name.startswith("~$") or path.name.startswith("."):
            return

        with db_lock:
            _ensure_thread_db()
            try:
                if event_type == "deleted":
                    watcher_pipeline.remove_file(path)  # type: ignore[union-attr]
                    print(f"\n   [indexer] removed: {path.name}")
                elif event_type in ("created", "modified"):
                    watcher_pipeline.reindex_file(path)  # type: ignore[union-attr]
                    print(f"\n   [indexer] indexed: {path.name}")
            except Exception as e:
                logger.warning("Watch event failed for %s: %s", path.name, e)

    watcher = FileWatcher(watched_folders=[kb_path], on_change=on_change)
    watcher.start()
    return watcher


def _create_llm_backend(decision: RuntimeDecision) -> MLXRuntime:
    """Create LLM runtime with MLX primary, Ollama fallback.

    Per Spec Section 1.1:
      - Default inference backend: MLX
      - Compatibility backend: llama.cpp
    """
    # --- Try MLX primary ---
    if decision.backend == "mlx":
        try:
            from jarvis.runtime.mlx_backend import MLXBackend
            backend = MLXBackend()
            backend.load(decision)
            print(f"   Backend: MLX ({backend.model_id})")
            return MLXRuntime(backend=backend, model_id=decision.model_id)
        except Exception as e:
            logger.warning("MLX backend failed: %s — falling back to Ollama", e)

    # --- Fallback to Ollama (llama.cpp) ---
    try:
        from jarvis.runtime.llamacpp_backend import LlamaCppBackend
        backend = LlamaCppBackend()
        fallback_decision = RuntimeDecision(
            tier=decision.tier,
            backend="llamacpp",
            model_id=decision.model_id,
            context_window=decision.context_window,
            reasoning_enabled=decision.reasoning_enabled,
        )
        backend.load(fallback_decision)
        print(f"   Backend: Ollama ({backend.model_id})")
        return MLXRuntime(backend=backend, model_id=decision.model_id)
    except Exception as e:
        logger.warning("Ollama backend failed: %s — falling back to stub", e)

    # --- Stub fallback ---
    print("   Backend: stub (no LLM available)")
    return MLXRuntime(model_id="stub")


def main() -> None:
    logging.basicConfig(
        level=logging.ERROR,
        format="%(levelname)s %(name)s: %(message)s",
    )

    result = bootstrap()

    # Model selection — default: qwen3:30b-a3b (best table/reasoning quality)
    model_id = "qwen3:30b-a3b"
    if len(sys.argv) > 1 and sys.argv[1].startswith("--model="):
        model_id = sys.argv[1].split("=", 1)[1]

    print(f"\n🤖 JARVIS v0.1.0")
    print(f"   LLM: {model_id} (MLX primary → Ollama fallback)")

    # Index knowledge base if available
    watcher = None
    if _DEFAULT_KB_PATH.exists():
        chunk_count, pipeline = _run_indexing(result.db, _DEFAULT_KB_PATH)
        print(f"   Knowledge base: {_DEFAULT_KB_PATH.name}/ ({chunk_count} chunks)")
        # Start real-time file watcher (Spec Task 1.2)
        watcher = _start_file_watcher(result.db, _DEFAULT_KB_PATH)
        print("   File watcher: active (실시간 인덱싱)")
    else:
        print(f"   Knowledge base: not found ({_DEFAULT_KB_PATH})")

    # Retrieval DB
    has_data = _has_indexed_data(result.db)
    retrieval_db = result.db if has_data else None
    if not has_data:
        print("   Retrieval: stub mode (인덱싱된 데이터 없음)")

    # Governor: real system state sampling per Spec Task 0.2
    governor = Governor()
    gov_state = governor.sample()
    print(f"   System: mem={gov_state.memory_pressure_pct:.0f}%, "
          f"swap={gov_state.swap_used_mb}MB, "
          f"thermal={gov_state.thermal_state}, "
          f"battery={gov_state.battery_pct}%")

    decision = governor.select_runtime(requested_tier="balanced")
    # Override model_id if user specified or governor returned empty
    if model_id != decision.model_id or not decision.model_id:
        decision = RuntimeDecision(
            tier=decision.tier,
            backend=decision.backend,
            model_id=model_id,
            context_window=decision.context_window,
            reasoning_enabled=decision.reasoning_enabled,
        )

    llm_generator = _create_llm_backend(decision)

    # Planner: AI-based intent classification per Spec Section 2.1
    # Uses fast model (exaone) for quick query analysis
    from jarvis.core.planner import Planner
    planner = Planner(model_id="exaone3.5:7.8b")

    orchestrator = Orchestrator(
        governor=governor,
        query_decomposer=QueryDecomposer(),
        fts_retriever=FTSIndex(db=retrieval_db),
        vector_retriever=VectorIndex(),
        hybrid_fusion=HybridSearch(),
        evidence_builder=EvidenceBuilder(db=retrieval_db),
        llm_generator=llm_generator,
        tool_registry=ToolRegistry(),
        conversation_store=ConversationStore(db=result.db),
        task_log_store=TaskLogStore(db=result.db),
        planner=planner,
    )

    repl = JarvisREPL(orchestrator)
    try:
        repl.start()
    finally:
        if watcher is not None:
            watcher.stop()  # type: ignore[union-attr]


if __name__ == "__main__":
    main()
