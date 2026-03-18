"""Shared runtime bootstrap for CLI, voice, and menu bar entrypoints."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from jarvis.app.bootstrap import BootstrapResult, bootstrap
from jarvis.app.config import JarvisConfig
from jarvis.contracts import RuntimeDecision
from jarvis.core.error_monitor import ErrorMonitor
from jarvis.core.governor import Governor
from jarvis.core.orchestrator import Orchestrator
from jarvis.core.tool_registry import ToolRegistry
from jarvis.memory.conversation_store import ConversationStore
from jarvis.memory.task_log import TaskLogStore
from jarvis.observability.metrics import MetricName, MetricsCollector
from jarvis.retrieval.evidence_builder import EvidenceBuilder
from jarvis.retrieval.fts_index import FTSIndex
from jarvis.retrieval.hybrid_search import HybridSearch
from jarvis.retrieval.query_decomposer import QueryDecomposer
from jarvis.retrieval.vector_index import VectorIndex
from jarvis.runtime.embedding_runtime import EmbeddingRuntime
from jarvis.runtime.mlx_runtime import MLXRuntime
from jarvis.runtime.model_router import ModelRouter

logger = logging.getLogger(__name__)

_DEFAULT_KB_PATH = Path("/Users/codingstudio/__PROJECTHUB__/JARVIS/knowledge_base")


@dataclass
class RuntimeContext:
    """Resolved runtime dependencies for an interactive JARVIS session."""

    bootstrap_result: BootstrapResult
    error_monitor: ErrorMonitor
    governor: Governor
    orchestrator: Orchestrator
    model_router: ModelRouter
    vector_index: VectorIndex
    watcher: object | None = None
    chunk_count: int = 0
    knowledge_base_path: Path | None = None


def is_indexable(path: Path) -> bool:
    """Check if a file can be indexed."""
    from jarvis.indexing.parsers import is_indexable as _is_indexable

    return _is_indexable(path)


def has_indexed_data(db: object) -> bool:
    """Check if the database has any indexed chunks."""
    try:
        row = db.execute("SELECT COUNT(*) FROM chunks").fetchone()  # type: ignore[union-attr]
        return row[0] > 0  # type: ignore[index]
    except Exception:
        return False


def create_pipeline(
    db: object,
    vector_index: object | None = None,
    metrics: MetricsCollector | None = None,
) -> object:
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
        vector_index=vector_index,
        metrics=metrics,
    )


def run_indexing(
    db: object,
    kb_path: Path,
    *,
    governor: Governor | None = None,
    metrics: MetricsCollector | None = None,
    error_monitor: ErrorMonitor | None = None,
    reporter: Callable[[str], None] | None = None,
) -> tuple[int, object]:
    """Index files in the knowledge base directory."""
    pipeline = create_pipeline(db, metrics=metrics)

    stale_rows = db.execute(  # type: ignore[union-attr]
        "SELECT document_id, path FROM documents WHERE indexing_status = 'INDEXED'"
    ).fetchall()
    stale_count = 0
    for doc_id, doc_path in stale_rows:
        if not Path(doc_path).exists():
            db.execute("DELETE FROM chunks WHERE document_id = ?", (doc_id,))  # type: ignore[union-attr]
            db.execute(  # type: ignore[union-attr]
                "UPDATE documents SET indexing_status = 'TOMBSTONED' WHERE document_id = ?",
                (doc_id,),
            )
            stale_count += 1
    if stale_count:
        db.commit()  # type: ignore[union-attr]
        if reporter is not None:
            reporter(f"   Cleaned up {stale_count} stale documents")

    files = [f for f in kb_path.rglob("*") if f.is_file() and is_indexable(f)]

    for path in files:
        if error_monitor is not None and error_monitor.read_only_mode:
            break
        if governor is not None and governor.should_pause_indexing():
            if reporter is not None:
                reporter("   Indexing paused by Governor (thermal/battery)")
            break
        if governor is not None and governor.should_backoff_indexing():
            time.sleep(0.1)
        try:
            pipeline.index_file(path)  # type: ignore[union-attr]
        except Exception as exc:
            if error_monitor is not None:
                lower_exc = str(exc).lower()
                if "locked" in lower_exc:
                    code = "SQLITE_LOCK"
                elif "integrity" in lower_exc or "malformed" in lower_exc:
                    code = "SQLITE_INTEGRITY"
                else:
                    code = "INDEX_WRITE_FAILED"
                error_monitor.record_error(code, category="index")
            if reporter is not None:
                reporter(f"   Index failed: {path.name} ({exc})")
            logger.warning("Index failed for %s: %s", path.name, exc)

    total = db.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]  # type: ignore[union-attr]

    import threading

    def _backfill_morphemes() -> None:
        from jarvis.app.bootstrap import init_database
        from jarvis.app.config import JarvisConfig

        bg_db = init_database(JarvisConfig())
        bg_pipeline = create_pipeline(bg_db, metrics=metrics)
        total_updated = 0
        while True:
            if error_monitor is not None and error_monitor.read_only_mode:
                break
            if governor is not None and governor.should_pause_indexing():
                break
            if governor is not None and governor.should_backoff_indexing():
                time.sleep(0.25)
            updated = bg_pipeline.backfill_morphemes(batch_size=50)  # type: ignore[union-attr]
            total_updated += updated
            if updated == 0:
                break
        if total_updated > 0 and reporter is not None:
            reporter(f"   [morphemes] {total_updated} chunks 형태소 분석 완료")
        bg_db.close()  # type: ignore[union-attr]

    def _backfill_embeddings() -> None:
        from jarvis.app.bootstrap import init_database
        from jarvis.app.config import JarvisConfig
        from jarvis.retrieval.vector_index import VectorIndex as BackgroundVectorIndex
        from jarvis.runtime.embedding_runtime import EmbeddingRuntime as BackgroundEmbeddingRuntime

        bg_db = init_database(JarvisConfig())
        bg_embedding = BackgroundEmbeddingRuntime()
        bg_vector_index = BackgroundVectorIndex(
            embedding_runtime=bg_embedding,
            metrics=metrics,
        )
        bg_pipeline = create_pipeline(
            bg_db,
            vector_index=bg_vector_index,
            metrics=metrics,
        )
        total_updated = 0
        while True:
            if error_monitor is not None and error_monitor.read_only_mode:
                break
            if governor is not None and governor.should_pause_indexing():
                break
            if governor is not None and governor.should_backoff_indexing():
                time.sleep(0.25)
            updated = bg_pipeline.backfill_embeddings(batch_size=32)  # type: ignore[union-attr]
            total_updated += updated
            if updated == 0:
                break
        if total_updated > 0 and reporter is not None:
            reporter(f"   [embeddings] {total_updated} chunks 임베딩 생성 완료")
        bg_embedding.unload_model()
        bg_db.close()  # type: ignore[union-attr]

    threading.Thread(target=_backfill_morphemes, daemon=True).start()
    threading.Thread(target=_backfill_embeddings, daemon=True).start()
    return total, pipeline


def start_file_watcher(
    kb_path: Path,
    *,
    governor: Governor | None = None,
    metrics: MetricsCollector | None = None,
    error_monitor: ErrorMonitor | None = None,
    reporter: Callable[[str], None] | None = None,
) -> object:
    """Start a watcher for real-time indexing."""
    import threading

    from jarvis.app.bootstrap import init_database
    from jarvis.app.config import JarvisConfig
    from jarvis.indexing.file_watcher import FileWatcher

    config = JarvisConfig()
    watcher_db: object | None = None
    watcher_pipeline: object | None = None
    db_lock = threading.Lock()
    pending_events = 0

    def _ensure_thread_db() -> None:
        nonlocal watcher_db, watcher_pipeline
        if watcher_db is None:
            watcher_db = init_database(config)
            watcher_pipeline = create_pipeline(watcher_db, metrics=metrics)

    def on_change(path: Path, event_type: str, dest_path: Path | None = None) -> None:
        nonlocal pending_events
        if path.name.startswith("~$") or path.name.startswith("."):
            return

        with db_lock:
            pending_events += 1
            _ensure_thread_db()
            assert watcher_pipeline is not None
            try:
                if error_monitor is not None and error_monitor.read_only_mode:
                    return
                if governor is not None and governor.should_pause_indexing():
                    if reporter is not None:
                        reporter(f"   [indexer] paused by Governor: {path.name}")
                    return
                if governor is not None and governor.should_backoff_indexing():
                    time.sleep(0.2)
                if event_type == "dir_deleted":
                    count = watcher_pipeline.remove_directory(path)  # type: ignore[union-attr]
                    if count and reporter is not None:
                        reporter(f"   [indexer] dir removed: {path.name}/ ({count} files)")
                elif event_type == "dir_moved" and dest_path is not None:
                    count = watcher_pipeline.move_directory(path, dest_path)  # type: ignore[union-attr]
                    if count and reporter is not None:
                        reporter(
                            f"   [indexer] dir moved: {path.name}/ → {dest_path.name}/ ({count} files)"
                        )
                elif event_type == "moved" and dest_path is not None:
                    watcher_pipeline.move_file(path, dest_path)  # type: ignore[union-attr]
                    if reporter is not None:
                        reporter(f"   [indexer] moved: {path.name} → {dest_path.name}")
                elif event_type == "deleted":
                    watcher_pipeline.remove_file(path)  # type: ignore[union-attr]
                    if reporter is not None:
                        reporter(f"   [indexer] removed: {path.name}")
                elif event_type in ("created", "modified"):
                    if not is_indexable(path):
                        return
                    watcher_pipeline.reindex_file(path)  # type: ignore[union-attr]
                    if reporter is not None:
                        reporter(f"   [indexer] indexed: {path.name}")
            except Exception as exc:
                if error_monitor is not None:
                    lower_exc = str(exc).lower()
                    if "locked" in lower_exc:
                        code = "SQLITE_LOCK"
                    elif "integrity" in lower_exc or "malformed" in lower_exc:
                        code = "SQLITE_INTEGRITY"
                    else:
                        code = "INDEX_WRITE_FAILED"
                    error_monitor.record_error(code, category="index")
                if reporter is not None:
                    reporter(f"   [indexer] {event_type} failed: {path.name} ({exc})")
                logger.warning("Watch event failed for %s: %s", path.name, exc)
            finally:
                pending_events = max(0, pending_events - 1)

    watcher = FileWatcher(watched_folders=[kb_path], on_change=on_change)
    watcher.start()
    setattr(watcher, "pending_event_count", lambda: pending_events)
    return watcher


def create_llm_backend(
    decision: RuntimeDecision,
    *,
    metrics: MetricsCollector | None = None,
    error_monitor: ErrorMonitor | None = None,
    reporter: Callable[[str], None] | None = None,
    allow_mlx: bool = True,
) -> MLXRuntime:
    """Create the LLM runtime with MLX primary and llama.cpp fallback."""
    max_context_chars = max(2048, (decision.context_window // 2) * 4)
    if decision.backend == "mlx" and allow_mlx:
        for attempt in range(2):
            try:
                from jarvis.runtime.mlx_backend import MLXBackend

                backend = MLXBackend()
                backend.load(decision)
                if reporter is not None:
                    reporter(f"   Backend: MLX ({backend.model_id})")
                return MLXRuntime(
                    backend=backend,
                    model_id=decision.model_id,
                    max_context_chars=max_context_chars,
                    metrics=metrics,
                )
            except Exception as exc:
                if metrics is not None:
                    metrics.increment(MetricName.MODEL_LOAD_FAILURE_COUNT)
                if error_monitor is not None:
                    error_monitor.record_error("MODEL_LOAD_FAILED", category="model")
                logger.warning("MLX backend failed (attempt %d): %s", attempt + 1, exc)

    try:
        from jarvis.runtime.llamacpp_backend import LlamaCppBackend

        backend = LlamaCppBackend()
        fallback_decision = RuntimeDecision(
            tier=decision.tier,
            backend="llamacpp",
            model_id=decision.model_id,
            context_window=decision.context_window,
            max_retrieved_chunks=decision.max_retrieved_chunks,
            generation_timeout_ms=decision.generation_timeout_ms,
            reasoning_enabled=decision.reasoning_enabled,
        )
        backend.load(fallback_decision)
        if reporter is not None:
            reporter(f"   Backend: Ollama ({backend.model_id})")
        return MLXRuntime(
            backend=backend,
            model_id=decision.model_id,
            max_context_chars=max_context_chars,
            metrics=metrics,
        )
    except Exception as exc:
        if metrics is not None:
            metrics.increment(MetricName.MODEL_LOAD_FAILURE_COUNT)
        if error_monitor is not None:
            error_monitor.record_error("MODEL_LOAD_FAILED", category="model")
        logger.warning("Ollama backend failed: %s — falling back to stub", exc)

    if reporter is not None:
        reporter("   Backend: stub (no LLM available)")
    return MLXRuntime(model_id="stub", max_context_chars=max_context_chars, metrics=metrics)


def build_runtime_context(
    *,
    model_id: str = "qwen3:14b",
    knowledge_base_path: Path = _DEFAULT_KB_PATH,
    start_watcher_enabled: bool = True,
    reporter: Callable[[str], None] | None = None,
    allow_mlx: bool = True,
    data_dir: Path | None = None,
) -> RuntimeContext:
    """Build the shared runtime dependency graph."""
    config = JarvisConfig(data_dir=data_dir) if data_dir is not None else None
    result = bootstrap(config)
    error_monitor = ErrorMonitor()
    watcher_pending = lambda: 0
    governor = Governor(
        metrics=result.metrics,
        indexing_queue_depth_provider=lambda: watcher_pending(),
    )

    chunk_count = 0
    watcher = None
    if knowledge_base_path.exists():
        chunk_count, _ = run_indexing(
            result.db,
            knowledge_base_path,
            governor=governor,
            metrics=result.metrics,
            error_monitor=error_monitor,
            reporter=reporter,
        )
        if start_watcher_enabled:
            watcher = start_file_watcher(
                knowledge_base_path,
                governor=governor,
                metrics=result.metrics,
                error_monitor=error_monitor,
                reporter=reporter,
            )
            watcher_pending = getattr(watcher, "pending_event_count", watcher_pending)
    elif reporter is not None:
        reporter(f"   Knowledge base: not found ({knowledge_base_path})")

    retrieval_db = result.db if has_indexed_data(result.db) else None

    decision = governor.select_runtime(requested_tier=governor.suggest_idle_requested_tier())
    if model_id != decision.model_id or not decision.model_id:
        decision = RuntimeDecision(
            tier=decision.tier,
            backend=decision.backend,
            model_id=model_id,
            context_window=decision.context_window,
            max_retrieved_chunks=decision.max_retrieved_chunks,
            generation_timeout_ms=decision.generation_timeout_ms,
            reasoning_enabled=decision.reasoning_enabled,
        )

    llm_generator = create_llm_backend(
        decision,
        metrics=result.metrics,
        error_monitor=error_monitor,
        reporter=reporter,
        allow_mlx=allow_mlx,
    )
    model_router = ModelRouter(memory_limit_gb=16.0)

    from jarvis.core.planner import Planner

    planner = Planner(model_id="exaone3.5:7.8b")
    vector_index = VectorIndex(
        embedding_runtime=EmbeddingRuntime(),
        metrics=result.metrics,
    )
    orchestrator = Orchestrator(
        governor=governor,
        query_decomposer=QueryDecomposer(),
        fts_retriever=FTSIndex(db=retrieval_db, metrics=result.metrics),
        vector_retriever=vector_index,
        hybrid_fusion=HybridSearch(),
        evidence_builder=EvidenceBuilder(db=retrieval_db, metrics=result.metrics),
        llm_generator=llm_generator,
        tool_registry=ToolRegistry(error_monitor=error_monitor),
        conversation_store=ConversationStore(db=result.db),
        task_log_store=TaskLogStore(db=result.db),
        planner=planner,
        metrics=result.metrics,
        error_monitor=error_monitor,
    )

    return RuntimeContext(
        bootstrap_result=result,
        error_monitor=error_monitor,
        governor=governor,
        orchestrator=orchestrator,
        model_router=model_router,
        vector_index=vector_index,
        watcher=watcher,
        chunk_count=chunk_count,
        knowledge_base_path=knowledge_base_path if knowledge_base_path.exists() else None,
    )


def shutdown_runtime_context(context: RuntimeContext) -> None:
    """Release long-lived resources for a runtime context."""
    if context.watcher is not None:
        context.watcher.stop()  # type: ignore[union-attr]
    try:
        context.vector_index._embedding_runtime.unload_model()  # type: ignore[attr-defined]
    except Exception:
        pass
    context.bootstrap_result.db.close()
