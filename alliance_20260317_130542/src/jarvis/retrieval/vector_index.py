"""VectorIndex — vector similarity retrieval via LanceDB.

Implements VectorRetrieverProtocol for dense vector search
over document chunk embeddings.

Per Spec: LanceDB serverless file-based vector DB.
Falls back to empty results if lancedb is not installed.
"""
from __future__ import annotations

import logging
import threading
import time
from pathlib import Path
from typing import Sequence

from jarvis.contracts import TypedQueryFragment, VectorHit, VectorRetrieverProtocol
from jarvis.observability.metrics import MetricName, MetricsCollector

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
        metrics: MetricsCollector | None = None,
    ) -> None:
        self._db_path = db_path or _DEFAULT_DB_PATH
        self._embedding_runtime = embedding_runtime
        self._table_name = table_name
        self._metrics = metrics
        self._db: object | None = None
        self._available: bool | None = None
        self._lock = threading.Lock()

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
        """Add or update vectors in the index (thread-safe)."""
        db = self._ensure_db()
        if db is None or not embeddings or not chunk_ids:
            return

        data = [
            {"chunk_id": cid, "document_id": did, "vector": vec}
            for cid, did, vec in zip(chunk_ids, document_ids, embeddings)
        ]

        with self._lock:
            try:
                table = self._get_table()
                if table is not None:
                    # Validate and delete existing entries
                    safe_ids = [cid for cid in set(chunk_ids) if '"' not in cid]
                    if safe_ids:
                        try:
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
        """Remove vectors by chunk_id (thread-safe)."""
        table = self._get_table()
        if table is None or not chunk_ids:
            return
        with self._lock:
            try:
                safe_ids = [cid for cid in chunk_ids if '"' not in cid]
                if not safe_ids:
                    return
                filter_expr = " OR ".join(f'chunk_id = "{cid}"' for cid in safe_ids)
                table.delete(filter_expr)  # type: ignore[union-attr]
            except Exception as e:
                logger.warning("Failed to remove vectors: %s", e)

    def remove_document(self, document_id: str) -> None:
        """Remove all vectors for a document_id (thread-safe)."""
        table = self._get_table()
        if table is None or not document_id or '"' in document_id:
            return
        with self._lock:
            try:
                table.delete(f'document_id = "{document_id}"')  # type: ignore[union-attr]
            except Exception as e:
                logger.warning("Failed to remove document vectors: %s", e)

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

        started_at = time.perf_counter()

        # Embed query
        try:
            query_vectors = self._embedding_runtime.embed([query_text])  # type: ignore[union-attr]
            if not query_vectors or all(v == 0.0 for v in query_vectors[0][:10]):
                return []  # Stub embedding — skip vector search
            query_vec = query_vectors[0]
        except Exception as e:
            logger.warning("Query embedding failed: %s", e)
            return []

        # ANN search (lock prevents concurrent write corruption)
        with self._lock:
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
            score = max(0.0, 1.0 - distance)
            hits.append(VectorHit(
                chunk_id=row["chunk_id"],
                document_id=row["document_id"],
                score=score,
                embedding_distance=distance,
            ))

        if self._metrics is not None:
            elapsed_ms = (time.perf_counter() - started_at) * 1000
            self._metrics.record(
                MetricName.QUERY_LATENCY_MS,
                elapsed_ms,
                tags={"stage": "vector_search", "result_count": str(len(hits))},
            )
        return hits
