"""EmbeddingRuntime — local embedding generation via sentence-transformers.

Implements EmbeddingRuntimeProtocol. Uses BGE-M3 on MPS (Apple Silicon)
for 1024-dimensional multilingual embeddings.

Per Spec Section 11.2: on-demand load/unload with Governor integration.
Falls back to stub (zero-vectors) if sentence-transformers is not installed.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Sequence

from jarvis.contracts import EmbeddingRuntimeProtocol

logger = logging.getLogger(__name__)

_DEFAULT_MODEL = "BAAI/bge-m3"
_DEFAULT_DIM = 1024
_BATCH_SIZE = 32
_DEFAULT_DEVICE = "cpu"


def _resolve_local_model_path(model_id: str) -> str | None:
    """Prefer a complete local Hugging Face snapshot when available."""
    if "/" not in model_id:
        return None

    org, name = model_id.split("/", 1)
    cache_root = Path.home() / ".cache" / "huggingface" / "hub"
    snapshot_root = cache_root / f"models--{org}--{name}" / "snapshots"
    if not snapshot_root.exists():
        return None

    snapshots = sorted(
        (
            path for path in snapshot_root.iterdir()
            if path.is_dir() and (path / "config.json").exists()
        ),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    for snapshot in snapshots:
        if any(snapshot.iterdir()):
            return str(snapshot)
    return None


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
        device: str | None = None,
    ) -> None:
        self._model_id = model_id
        self._dim = dim
        self._device = device or os.getenv("JARVIS_EMBEDDING_DEVICE", _DEFAULT_DEVICE)
        self._model: object | None = None
        self._available: bool | None = None

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
            os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
            os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")
            logging.getLogger("sentence_transformers").setLevel(logging.ERROR)
            logging.getLogger("transformers").setLevel(logging.ERROR)
            logging.getLogger("huggingface_hub").setLevel(logging.ERROR)
            try:
                from huggingface_hub.utils import disable_progress_bars

                disable_progress_bars()
            except Exception:
                pass
            from sentence_transformers import SentenceTransformer
            model_source = _resolve_local_model_path(self._model_id) or self._model_id
            self._model = SentenceTransformer(model_source, device=self._device)
            logger.info("Loaded embedding model: %s on %s", model_source, self._device)
        except Exception as e:
            logger.warning("Failed to load embedding model: %s", e)
            self._available = False

    def unload_model(self) -> None:
        """Unload model and free memory."""
        if self._model is None:
            return
        del self._model
        self._model = None
        if self._device.startswith("mps"):
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

        if self._model is None:
            self.load_model()

        if self._model is None:
            return [[0.0] * self._dim for _ in texts]

        try:
            import numpy as np
            embeddings = self._model.encode(
                list(texts),
                batch_size=_BATCH_SIZE,
                show_progress_bar=False,
                normalize_embeddings=True,
            )
            if isinstance(embeddings, np.ndarray):
                return embeddings.tolist()
            return [list(map(float, v)) for v in embeddings]
        except Exception as e:
            logger.warning("Embedding failed: %s — returning zero vectors", e)
            return [[0.0] * self._dim for _ in texts]
