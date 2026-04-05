"""Gemma VLM Backend — LLM backend for Google Gemma 4 family using mlx_vlm.

Implements LLMBackendProtocol per Implementation Spec Section 2.2.
Uses mlx_vlm (not mlx_lm) because Gemma 4 models are vision-language models
requiring the multimodal processor. Text-only inference is supported by
passing num_images=0 to the chat template.

Benchmark (2026-04-05, M1 Max, 4-bit quantization):
- Gemma 4 E4B:  RAG 9/9 keywords, 2.1s avg, 5.3GB peak, 128K context
- Gemma 4 E2B:  103 tok/s, 3.6GB peak, 128K context
"""

from __future__ import annotations

import logging
import time
from collections.abc import Iterator

from jarvis.contracts import LLMBackendProtocol, RuntimeDecision
from jarvis.runtime.model_router import ModelRouter

logger = logging.getLogger(__name__)

# Model ID mapping: short alias -> HuggingFace repo
_MODEL_ALIASES: dict[str, str] = {
    # Gemma 4 (multimodal, 128K context)
    "gemma4:e2b": "mlx-community/gemma-4-E2B-it-4bit",
    "gemma4:e4b": "mlx-community/gemma-4-E4B-it-4bit",
    # Legacy aliases
    "gemma-4-e2b": "mlx-community/gemma-4-E2B-it-4bit",
    "gemma-4-e4b": "mlx-community/gemma-4-E4B-it-4bit",
}


def _resolve_model_id(model_id: str) -> str:
    """Resolve short alias to full HuggingFace repo path."""
    return _MODEL_ALIASES.get(model_id, model_id)


def is_gemma_vlm_model(model_id: str) -> bool:
    """Check if the model_id refers to a Gemma VLM model."""
    resolved = _resolve_model_id(model_id)
    return "gemma-4" in resolved.lower() or "gemma4" in model_id.lower()


class GemmaVlmBackend:
    """MLX-VLM based backend for Gemma 4 models on Apple Silicon.

    Implements LLMBackendProtocol.
    Uses mlx_vlm for model loading and text generation (text-only path).
    """

    def __init__(
        self,
        *,
        model_router: ModelRouter | None = None,
        estimated_memory_gb: float = 6.0,
    ) -> None:
        self._model: object | None = None
        self._processor: object | None = None
        self._config: object | None = None
        self._model_id: str = ""
        self._context_window: int = 131072  # 128K default for Gemma 4
        self._model_router = model_router
        self._estimated_memory_gb = estimated_memory_gb
        self._router_model_id: str | None = None

    @property
    def is_loaded(self) -> bool:
        return self._model is not None

    @property
    def model_id(self) -> str:
        return self._model_id

    def load(self, decision: RuntimeDecision) -> None:
        """Load the Gemma 4 model specified by RuntimeDecision."""
        repo_id = _resolve_model_id(decision.model_id)

        if self._model is not None and self._model_id == repo_id:
            logger.info("Gemma model %s already loaded, skipping.", repo_id)
            return

        if self._model is not None:
            self.unload()

        if self._model_router is not None:
            granted = self._model_router.request_load(repo_id, self._estimated_memory_gb)
            if not granted:
                raise RuntimeError(f"ModelRouter denied loading Gemma VLM model: {repo_id}")

        logger.info("Loading Gemma VLM model: %s", repo_id)
        t0 = time.perf_counter()

        # Suppress stdout noise that could corrupt JSON bridge output.
        import os as _os
        import sys as _sys
        saved_stdout = _sys.stdout
        _sys.stdout = open(_os.devnull, "w")
        try:
            from mlx_vlm import load as vlm_load
            from mlx_vlm.utils import load_config
            self._model, self._processor = vlm_load(repo_id)
            self._config = load_config(repo_id)
        finally:
            _sys.stdout.close()
            _sys.stdout = saved_stdout

        elapsed = time.perf_counter() - t0
        self._model_id = repo_id
        self._router_model_id = repo_id
        self._context_window = decision.context_window
        logger.info("Gemma model loaded in %.1fs: %s", elapsed, repo_id)

    def unload(self) -> None:
        """Unload the current model and release memory."""
        if self._model is None:
            return

        model_id = self._model_id
        logger.info("Unloading Gemma VLM model: %s", model_id)

        self._model = None
        self._processor = None
        self._config = None
        self._model_id = ""
        if self._model_router is not None and self._router_model_id is not None:
            self._model_router.release(self._router_model_id)
        self._router_model_id = None

        # Force Metal memory reclaim
        try:
            import mlx.core as mx
            if hasattr(mx, "clear_cache"):
                mx.clear_cache()
            else:
                mx.metal.clear_cache()
        except Exception:
            pass

        logger.info("Gemma model unloaded: %s", model_id)

    def generate(self, prompt: str, context: str, intent: str) -> str:
        """Generate a response given prompt, context, and intent."""
        if self._model is None or self._processor is None:
            raise RuntimeError("No Gemma model loaded. Call load() first.")

        from mlx_vlm import generate as vlm_generate
        from mlx_vlm.prompt_utils import apply_chat_template

        from jarvis.runtime.system_prompt import build_system_message
        system_message = build_system_message(context)

        # Combine system + user prompt (Gemma's chat template does not have
        # a dedicated system role; prepend it to the user message instead).
        full_prompt = f"{system_message}\n\n{prompt}"

        formatted_prompt = apply_chat_template(
            self._processor, self._config, full_prompt, num_images=0
        )

        # Dynamic max_tokens: reserve context for prompt
        try:
            prompt_tokens = len(self._processor.tokenizer.encode(formatted_prompt))
        except Exception:
            # Fallback: rough character-based estimate (4 chars per token)
            prompt_tokens = len(formatted_prompt) // 4
        _RESERVE = 256
        max_tokens = max(256, self._context_window - prompt_tokens - _RESERVE)
        logger.debug(
            "Gemma token budget: context=%d, prompt=%d, reserve=%d, max_tokens=%d",
            self._context_window, prompt_tokens, _RESERVE, max_tokens,
        )

        t0 = time.perf_counter()
        output = vlm_generate(
            self._model,
            self._processor,
            formatted_prompt,
            config=self._config,
            max_tokens=max_tokens,
            temperature=0.7,
            verbose=False,
        )
        elapsed_ms = (time.perf_counter() - t0) * 1000

        text = output.text if hasattr(output, "text") else str(output)
        logger.info(
            "Gemma generated %d chars in %.0fms (model=%s, intent=%s)",
            len(text), elapsed_ms, self._model_id, intent,
        )

        return text

    def generate_stream(self, prompt: str, context: str, intent: str) -> Iterator[str]:
        """Generate a response, yielding tokens for real-time display.

        mlx_vlm does not expose a stable stream_generate API as of 0.4.4,
        so this falls back to yielding the full response as a single chunk.
        """
        yield self.generate(prompt, context, intent)

    def generate_with_image(
        self,
        prompt: str,
        image_path: str,
        *,
        context: str = "",
        max_tokens: int = 1024,
    ) -> str:
        """Generate a response describing/answering about an image.

        Args:
            prompt: User question about the image.
            image_path: Absolute path to image file (PNG, JPG, etc).
            context: Optional RAG evidence context.
            max_tokens: Max output tokens.

        Returns:
            Generated response text.
        """
        if self._model is None or self._processor is None:
            raise RuntimeError("No Gemma model loaded. Call load() first.")

        from mlx_vlm import generate as vlm_generate
        from mlx_vlm.prompt_utils import apply_chat_template

        full_prompt = (
            f"{context}\n\n{prompt}" if context.strip() else prompt
        )

        formatted_prompt = apply_chat_template(
            self._processor, self._config, full_prompt, num_images=1
        )

        t0 = time.perf_counter()
        output = vlm_generate(
            self._model,
            self._processor,
            formatted_prompt,
            image=image_path,
            config=self._config,
            max_tokens=max_tokens,
            temperature=0.7,
            verbose=False,
        )
        elapsed_ms = (time.perf_counter() - t0) * 1000

        text = output.text if hasattr(output, "text") else str(output)
        logger.info(
            "Gemma vision generated %d chars in %.0fms (model=%s, image=%s)",
            len(text), elapsed_ms, self._model_id, image_path,
        )
        return text


# Runtime-checkable verification
assert isinstance(GemmaVlmBackend(), LLMBackendProtocol)
