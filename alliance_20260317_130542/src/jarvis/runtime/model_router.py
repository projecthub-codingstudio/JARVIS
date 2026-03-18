"""ModelRouter — routes model requests and manages sequential loading.

Ensures only one large model is in memory at a time (STT -> LLM -> TTS),
respecting the 15-20GB memory budget constraint.
"""

from __future__ import annotations


class ModelRouter:
    """Routes model load/unload requests to enforce sequential loading.

    Ensures memory budget is respected by loading at most one large
    model at a time. Coordinates between LLM, STT, and TTS runtimes.
    """

    def __init__(self, *, memory_limit_gb: float = 16.0) -> None:
        """Initialize with memory budget.

        Args:
            memory_limit_gb: Maximum memory budget for models in GB.
        """
        self._memory_limit_gb = memory_limit_gb
        self._active_model: str | None = None
        self._active_memory_gb: float = 0.0

    def request_load(self, model_id: str, estimated_memory_gb: float) -> bool:
        """Request to load a model. Unloads current model if needed.

        Args:
            model_id: Identifier for the model to load.
            estimated_memory_gb: Estimated memory footprint.

        Returns:
            True if the model can be loaded within budget.

        """
        if estimated_memory_gb <= 0:
            return False
        if estimated_memory_gb > self._memory_limit_gb:
            return False
        if self._active_model == model_id:
            self._active_memory_gb = estimated_memory_gb
            return True

        self._active_model = model_id
        self._active_memory_gb = estimated_memory_gb
        return True

    def release(self, model_id: str) -> None:
        """Release a loaded model from memory.

        Args:
            model_id: Identifier of the model to release.

        """
        if self._active_model == model_id:
            self._active_model = None
            self._active_memory_gb = 0.0

    @property
    def active_model(self) -> str | None:
        """Return the currently loaded model ID, or None."""
        return self._active_model

    @property
    def active_memory_gb(self) -> float:
        """Return the estimated memory used by the active model."""
        return self._active_memory_gb
