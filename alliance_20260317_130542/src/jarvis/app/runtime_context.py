"""Shared runtime bootstrap for CLI, voice, and menu bar entrypoints."""

from __future__ import annotations

import logging
import os
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
from jarvis.learning import schema_sql_path
from jarvis.learning.pattern_store import PatternStore
from jarvis.learning.coordinator import LearningCoordinator
from jarvis.learning.embedding_adapter import BgeM3Adapter
from jarvis.learning.batch_scheduler import BatchScheduler

logger = logging.getLogger(__name__)

_DEFAULT_KB_DIRNAME = "knowledge_base"


def _summarize_runtime_error(message: str) -> str:
    """Collapse multi-line runtime failures into a short health detail."""
    line = " ".join(part.strip() for part in message.splitlines() if part.strip())
    return line[:240]


def resolve_knowledge_base_path(candidate: Path | None = None) -> Path:
    """Resolve the effective knowledge base path.

    Priority:
      1. Explicit function argument
      2. JARVIS_KNOWLEDGE_BASE env var
      3. ./knowledge_base under the current working directory
    """
    if candidate is not None:
        return candidate.expanduser().resolve()

    env_value = os.getenv("JARVIS_KNOWLEDGE_BASE", "").strip()
    if env_value:
        return Path(env_value).expanduser().resolve()

    cwd = Path.cwd().resolve()
    search_roots = [cwd, *list(cwd.parents)[:4]]
    for root in search_roots:
        kb_path = (root / _DEFAULT_KB_DIRNAME).resolve()
        if kb_path.exists():
            return kb_path

    return (cwd / _DEFAULT_KB_DIRNAME).resolve()


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


class NoOpVectorIndex:
    """Lightweight vector retriever used for menu-bar stub queries."""

    _embedding_runtime = None

    def search(self, fragments, top_k: int = 10) -> list[object]:
        return []

    def add(self, chunk_ids: list[str], document_ids: list[str], embeddings: list[list[float]]) -> None:
        return None

    def remove(self, chunk_ids: list[str]) -> None:
        return None


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


def purge_documents_outside_knowledge_base(
    db: object,
    kb_path: Path,
    *,
    vector_index: object | None = None,
    reporter: Callable[[str], None] | None = None,
) -> int:
    """Remove indexed metadata for documents outside the active knowledge base."""
    rows = db.execute(  # type: ignore[union-attr]
        "SELECT document_id, path FROM documents WHERE indexing_status != 'TOMBSTONED'"
    ).fetchall()

    removed_count = 0
    resolved_kb_path = kb_path.expanduser().resolve()
    for document_id, document_path in rows:
        try:
            resolved_document_path = Path(document_path).expanduser().resolve()
            resolved_document_path.relative_to(resolved_kb_path)
        except ValueError:
            chunk_rows = db.execute(  # type: ignore[union-attr]
                "SELECT chunk_id FROM chunks WHERE document_id = ?",
                (document_id,),
            ).fetchall()
            chunk_ids = [row[0] for row in chunk_rows]
            if chunk_ids and vector_index is not None:
                vector_index.remove(chunk_ids)  # type: ignore[union-attr]
            db.execute("DELETE FROM chunks WHERE document_id = ?", (document_id,))  # type: ignore[union-attr]
            db.execute("DELETE FROM documents WHERE document_id = ?", (document_id,))  # type: ignore[union-attr]
            removed_count += 1

    if removed_count:
        db.commit()  # type: ignore[union-attr]
        if reporter is not None:
            reporter(f"   Purged {removed_count} documents outside active knowledge base")
    return removed_count


def run_indexing(
    db: object,
    kb_path: Path,
    *,
    data_dir: Path | None = None,
    vector_index: object | None = None,
    start_background_backfill: bool = True,
    governor: Governor | None = None,
    metrics: MetricsCollector | None = None,
    error_monitor: ErrorMonitor | None = None,
    reporter: Callable[[str], None] | None = None,
) -> tuple[int, object]:
    """Index files in the knowledge base directory."""
    pipeline = create_pipeline(db, vector_index=vector_index, metrics=metrics)
    purge_documents_outside_knowledge_base(
        db,
        kb_path,
        vector_index=vector_index,
        reporter=reporter,
    )

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
    total_files = len(files)
    if reporter is not None:
        reporter(
            f"   Index scan: {total_files} indexable files in {kb_path.name}"
            if total_files > 0
            else f"   Index scan: no indexable files found in {kb_path.name}"
        )

    for index, path in enumerate(files, start=1):
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
            if reporter is not None:
                reporter(f"   Indexing {index}/{total_files}: {path.name}")
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
                reporter(f"   Index failed {index}/{total_files}: {path.name} ({exc})")
            logger.warning("Index failed for %s: %s", path.name, exc)

    total = db.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]  # type: ignore[union-attr]

    import threading

    def _backfill_morphemes() -> None:
        from jarvis.app.bootstrap import init_database
        from jarvis.app.config import JarvisConfig

        bg_db = None
        try:
            bg_db = init_database(JarvisConfig(data_dir=data_dir))
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
        except Exception as exc:
            logger.warning("Morpheme backfill failed: %s", exc)
        finally:
            if bg_db is not None:
                bg_db.close()  # type: ignore[union-attr]

    def _backfill_embeddings() -> None:
        from jarvis.app.bootstrap import init_database
        from jarvis.app.config import JarvisConfig

        bg_db = None
        try:
            bg_db = init_database(JarvisConfig(data_dir=data_dir))
            bg_pipeline = create_pipeline(
                bg_db,
                vector_index=vector_index,
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
        except Exception as exc:
            logger.warning("Embedding backfill failed: %s", exc)
        finally:
            if bg_db is not None:
                bg_db.close()  # type: ignore[union-attr]

    if start_background_backfill:
        threading.Thread(target=_backfill_morphemes, daemon=True).start()
        threading.Thread(target=_backfill_embeddings, daemon=True).start()
    return total, pipeline


def ensure_vector_index_ready(
    *,
    pipeline: object | None,
    vector_index: object | None,
    chunk_count: int,
    reporter: Callable[[str], None] | None = None,
) -> None:
    """Start background embedding backfill without blocking startup.

    Menu bar mode disables the standard background backfill. This function
    starts a daemon thread that loads the embedding model and backfills all
    missing embeddings. The server can start handling queries immediately
    (FTS still works without vectors).
    """
    if pipeline is None or vector_index is None or chunk_count <= 0:
        return

    import threading

    def _backfill_all() -> None:
        total = 0
        try:
            while True:
                batch = pipeline.backfill_embeddings(batch_size=64)  # type: ignore[attr-defined]
                total += batch
                if batch == 0:
                    break
        except Exception as exc:
            logger.warning("Background embedding backfill failed: %s", exc)
        if total > 0 and reporter is not None:
            reporter(f"   [embeddings] background backfill complete ({total} chunks)")

    threading.Thread(target=_backfill_all, daemon=True, name="embedding-backfill").start()


def start_file_watcher(
    kb_path: Path,
    *,
    data_dir: Path | None = None,
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

    config = JarvisConfig(data_dir=data_dir, watched_folders=[kb_path])
    watcher_db: object | None = None
    watcher_pipeline: object | None = None
    watcher_vector_index: object | None = None
    db_lock = threading.Lock()
    pending_events = 0

    def _ensure_thread_db() -> None:
        nonlocal watcher_db, watcher_pipeline, watcher_vector_index
        if watcher_db is None:
            watcher_db = init_database(config)
            watcher_vector_index = VectorIndex(
                db_path=config.data_dir / "vectors.lance",
                embedding_runtime=EmbeddingRuntime(),
                metrics=metrics,
            )
            watcher_pipeline = create_pipeline(
                watcher_db,
                vector_index=watcher_vector_index,
                metrics=metrics,
            )

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


def _create_user_knowledge_store(db):
    """Create the Tier 3 user knowledge store if the table exists."""
    try:
        from jarvis.memory.user_knowledge import UserKnowledgeStore
        return UserKnowledgeStore(db=db)
    except Exception:
        return None


def create_llm_backend(
    decision: RuntimeDecision,
    *,
    model_router: ModelRouter | None = None,
    metrics: MetricsCollector | None = None,
    error_monitor: ErrorMonitor | None = None,
    reporter: Callable[[str], None] | None = None,
    allow_mlx: bool = True,
) -> MLXRuntime:
    """Create the LLM runtime with MLX primary and llama.cpp fallback."""
    max_context_chars = max(2048, (decision.context_window // 2) * 4)
    if decision.model_id.strip().lower() == "stub":
        if reporter is not None:
            reporter("   Backend: stub (forced)")
        return MLXRuntime(
            model_id="stub",
            max_context_chars=max_context_chars,
            metrics=metrics,
            status_detail="forced stub backend",
        )

    fallback_reasons: list[str] = []
    estimated_memory_gb = _estimate_llm_memory_gb(decision)
    if decision.backend == "mlx" and allow_mlx:
        from jarvis.runtime.mlx_backend import mlx_import_probe

        mlx_ok, mlx_detail = mlx_import_probe()
        if not mlx_ok:
            summary = _summarize_runtime_error(mlx_detail or "unknown error")
            fallback_reasons.append(f"MLX preflight failed: {summary}")
            if metrics is not None:
                metrics.increment(MetricName.MODEL_LOAD_FAILURE_COUNT)
            if error_monitor is not None:
                error_monitor.record_error("MODEL_LOAD_FAILED", category="model")
            logger.warning("MLX preflight failed: %s", summary or "unknown error")
        else:
            for attempt in range(2):
                try:
                    from jarvis.runtime.gemma_vlm_backend import is_gemma_vlm_model
                    if is_gemma_vlm_model(decision.model_id):
                        from jarvis.runtime.gemma_vlm_backend import GemmaVlmBackend

                        backend = GemmaVlmBackend(
                            model_router=model_router,
                            estimated_memory_gb=estimated_memory_gb,
                        )
                        backend_label = "Gemma-VLM"
                    else:
                        from jarvis.runtime.mlx_backend import MLXBackend

                        backend = MLXBackend(
                            model_router=model_router,
                            estimated_memory_gb=estimated_memory_gb,
                        )
                        backend_label = "MLX"
                    backend.load(decision)
                    if reporter is not None:
                        reporter(f"   Backend: {backend_label} ({backend.model_id})")
                    return MLXRuntime(
                        backend=backend,
                        model_id=decision.model_id,
                        max_context_chars=max_context_chars,
                        metrics=metrics,
                        status_detail=f"OK ({backend.model_id})",
                    )
                except Exception as exc:
                    fallback_reasons.append(
                        f"MLX load failed (attempt {attempt + 1}): {_summarize_runtime_error(str(exc))}"
                    )
                    if metrics is not None:
                        metrics.increment(MetricName.MODEL_LOAD_FAILURE_COUNT)
                    if error_monitor is not None:
                        error_monitor.record_error("MODEL_LOAD_FAILED", category="model")
                    logger.warning("MLX backend failed (attempt %d): %s", attempt + 1, exc)

    try:
        from jarvis.runtime.llamacpp_backend import LlamaCppBackend

        backend = LlamaCppBackend(
            model_router=model_router,
            estimated_memory_gb=estimated_memory_gb,
        )
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
            status_detail=backend.status_detail,
        )
    except Exception as exc:
        fallback_reasons.append(f"Ollama fallback failed: {_summarize_runtime_error(str(exc))}")
        if metrics is not None:
            metrics.increment(MetricName.MODEL_LOAD_FAILURE_COUNT)
        if error_monitor is not None:
            error_monitor.record_error("MODEL_LOAD_FAILED", category="model")
        logger.warning("Ollama backend failed: %s — falling back to stub", exc)

    if reporter is not None:
        reporter("   Backend: stub (no LLM available)")
    return MLXRuntime(
        model_id="stub",
        max_context_chars=max_context_chars,
        metrics=metrics,
        status_detail=" | ".join(fallback_reasons) if fallback_reasons else "stub — no LLM loaded",
    )


def build_runtime_context(
    *,
    model_id: str = "qwen3.5:9b",
    knowledge_base_path: Path | None = None,
    start_watcher_enabled: bool = True,
    start_background_backfill: bool = True,
    reporter: Callable[[str], None] | None = None,
    allow_mlx: bool = True,
    data_dir: Path | None = None,
) -> RuntimeContext:
    """Build the shared runtime dependency graph."""
    lightweight_query_mode = model_id.strip().lower() == "stub"
    resolved_kb_path = resolve_knowledge_base_path(knowledge_base_path)
    watched_folders = [resolved_kb_path] if resolved_kb_path.exists() else []
    config = JarvisConfig(
        data_dir=data_dir if data_dir is not None else Path.home() / ".jarvis",
        watched_folders=watched_folders,
    )
    result = bootstrap(config)
    error_monitor = ErrorMonitor()
    watcher_pending = lambda: 0
    governor = Governor(
        metrics=result.metrics,
        indexing_queue_depth_provider=lambda: watcher_pending(),
    )
    if lightweight_query_mode:
        vector_index = NoOpVectorIndex()
    else:
        vector_index = VectorIndex(
            db_path=result.config.data_dir / "vectors.lance",
            embedding_runtime=EmbeddingRuntime(),
            metrics=result.metrics,
        )

    chunk_count = 0
    watcher = None
    if lightweight_query_mode:
        if has_indexed_data(result.db):
            row = result.db.execute("SELECT COUNT(*) FROM chunks").fetchone()
            chunk_count = int(row[0]) if row else 0
        if reporter is not None:
            reporter("   Indexing: skipped for lightweight query mode")
    elif resolved_kb_path.exists():
        chunk_count, pipeline = run_indexing(
            result.db,
            resolved_kb_path,
            data_dir=result.config.data_dir,
            vector_index=vector_index,
            start_background_backfill=start_background_backfill,
            governor=governor,
            metrics=result.metrics,
            error_monitor=error_monitor,
            reporter=reporter,
        )
        if not start_background_backfill and start_watcher_enabled:
            # Only run background vector backfill when watcher is active.
            # When watcher is disabled (menu-bar), skip to avoid LanceDB
            # stack overflow caused by concurrent thread writes.
            ensure_vector_index_ready(
                pipeline=pipeline,
                vector_index=vector_index,
                chunk_count=chunk_count,
                reporter=reporter,
            )
        if start_watcher_enabled:
            watcher = start_file_watcher(
                resolved_kb_path,
                data_dir=result.config.data_dir,
                governor=governor,
                metrics=result.metrics,
                error_monitor=error_monitor,
                reporter=reporter,
            )
            watcher_pending = getattr(watcher, "pending_event_count", watcher_pending)
    elif reporter is not None:
        reporter(f"   Knowledge base: not found ({resolved_kb_path})")

    retrieval_db = result.db if has_indexed_data(result.db) else None

    model_router = ModelRouter(memory_limit_gb=16.0)
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
        model_router=model_router,
        metrics=result.metrics,
        error_monitor=error_monitor,
        reporter=reporter,
        allow_mlx=allow_mlx,
    )

    from jarvis.core.planner import LLMIntentJSONBackend, Planner

    planner_backend = None
    llm_backend = getattr(llm_generator, "_backend", None)
    if llm_backend is not None:
        planner_backend = LLMIntentJSONBackend(llm_backend=llm_backend)

    # Initialize LearningCoordinator (optional, skips on error)
    learning_coordinator: object | None = None
    batch_scheduler: object | None = None
    try:
        schema_sql = Path(schema_sql_path()).read_text(encoding="utf-8")
        result.db.executescript(schema_sql)

        # Share the embedding runtime used by the vector index
        shared_embedding_runtime = EmbeddingRuntime()

        pattern_store = PatternStore(db=result.db)
        embedding_adapter = BgeM3Adapter(runtime=shared_embedding_runtime)
        learning_coordinator = LearningCoordinator(
            store=pattern_store,
            embed_fn=embedding_adapter.embed,
            similarity_fn=embedding_adapter.similarity,
        )
        learning_coordinator.refresh_index()
        logger.info("LearningCoordinator initialized")
    except Exception as exc:
        logger.warning("LearningCoordinator unavailable: %s", exc)
        learning_coordinator = None

    # Start batch scheduler
    if learning_coordinator is not None:
        try:
            batch_scheduler = BatchScheduler(
                coordinator=learning_coordinator,
                interval_seconds=600.0,
                lookback_seconds=300,
            )
            batch_scheduler.start()
            logger.info("Learning batch scheduler started (10-min interval)")
        except Exception as exc:
            logger.warning("Batch scheduler failed to start: %s", exc)
            batch_scheduler = None

    planner_kwargs: dict[str, object] = {
        "model_id": "qwen3.5:9b",
        "knowledge_base_path": resolved_kb_path,
        "learning_coordinator": learning_coordinator,
    }
    if planner_backend is not None:
        planner_kwargs["lightweight_backend"] = planner_backend
    planner = Planner(**planner_kwargs)

    # Cross-encoder reranker (lazy-loaded on first query)
    if lightweight_query_mode:
        reranker = None
        if reporter is not None:
            reporter("   Retrieval: lightweight FTS-only mode")
    else:
        from jarvis.retrieval.reranker import Reranker
        reranker = Reranker(metrics=result.metrics)

    orchestrator = Orchestrator(
        governor=governor,
        query_decomposer=QueryDecomposer(knowledge_base_path=resolved_kb_path),
        fts_retriever=FTSIndex(db=retrieval_db, metrics=result.metrics),
        vector_retriever=vector_index,
        hybrid_fusion=HybridSearch(),
        evidence_builder=EvidenceBuilder(db=retrieval_db, metrics=result.metrics),
        llm_generator=llm_generator,
        tool_registry=ToolRegistry(error_monitor=error_monitor),
        conversation_store=ConversationStore(db=result.db),
        task_log_store=TaskLogStore(db=result.db),
        planner=planner,
        reranker=reranker,
        metrics=result.metrics,
        error_monitor=error_monitor,
        user_knowledge_store=_create_user_knowledge_store(result.db),
        knowledge_base_path=resolved_kb_path,
        learning_coordinator=learning_coordinator,
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
        knowledge_base_path=resolved_kb_path if resolved_kb_path.exists() else None,
    )


def shutdown_runtime_context(context: RuntimeContext) -> None:
    """Release long-lived resources for a runtime context."""
    if context.watcher is not None:
        context.watcher.stop()  # type: ignore[union-attr]
    try:
        context.orchestrator._llm_generator.unload()  # type: ignore[attr-defined]
    except Exception:
        pass
    try:
        context.vector_index._embedding_runtime.unload_model()  # type: ignore[attr-defined]
    except Exception:
        pass
    context.bootstrap_result.db.close()


def _estimate_llm_memory_gb(decision: RuntimeDecision) -> float:
    """Rough memory estimate for model-router admission control."""
    model_id = decision.model_id.lower()
    if "32b" in model_id or decision.tier == "deep":
        return 14.0
    if "14b" in model_id:
        return 10.0
    if "9b" in model_id or "7.8b" in model_id:
        return 8.0
    if "1.2b" in model_id or "2.4b" in model_id:
        return 4.0
    return 8.0
