"""MLX Backend — primary LLM backend using mlx-lm on Apple Silicon.

Implements LLMBackendProtocol per Implementation Spec Section 2.2, Task 0.3.
Default inference backend. Sequential model loading enforced.
"""

from __future__ import annotations

import functools
import json
import logging
import subprocess
import sys
import time
from pathlib import Path

from jarvis.contracts import LLMBackendProtocol, RuntimeDecision

logger = logging.getLogger(__name__)
_MLX_PROBE_CACHE = Path("/tmp/jarvis_mlx_probe_status.json")
_MLX_PROBE_TTL_SECONDS = 60 * 60

# Model ID mapping: short alias -> HuggingFace repo
_MODEL_ALIASES: dict[str, str] = {
    "qwen3:14b": "mlx-community/Qwen3-14B-4bit",
    "qwen3-14b": "mlx-community/Qwen3-14B-4bit",
    "exaone3.5:7.8b": "mlx-community/EXAONE-3.5-7.8B-Instruct-4bit",
    "exaone-deep-7.8b": "mlx-community/EXAONE-3.5-7.8B-Instruct-4bit",
}


def _resolve_model_id(model_id: str) -> str:
    """Resolve short alias to full HuggingFace repo path."""
    return _MODEL_ALIASES.get(model_id, model_id)


@functools.lru_cache(maxsize=1)
def mlx_import_probe() -> tuple[bool, str]:
    """Check whether mlx_lm can be imported safely in a subprocess."""
    cached = _read_probe_cache()
    if cached is not None:
        return cached

    result = subprocess.run(
        [sys.executable, "-c", "import mlx_lm"],
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    if result.returncode == 0:
        _write_probe_cache(True, "")
        return True, ""
    stderr = (result.stderr or result.stdout).strip()
    detail = stderr[:240]
    _write_probe_cache(False, detail)
    return False, detail


def _read_probe_cache() -> tuple[bool, str] | None:
    try:
        if not _MLX_PROBE_CACHE.exists():
            return None
        payload = json.loads(_MLX_PROBE_CACHE.read_text(encoding="utf-8"))
        timestamp = float(payload.get("timestamp", 0))
        if time.time() - timestamp > _MLX_PROBE_TTL_SECONDS:
            return None
        ok = bool(payload.get("ok", False))
        if ok:
            return None
        return ok, str(payload.get("detail", ""))
    except Exception:
        return None


def _write_probe_cache(ok: bool, detail: str) -> None:
    if ok:
        return
    try:
        _MLX_PROBE_CACHE.write_text(
            json.dumps({
                "ok": ok,
                "detail": detail,
                "timestamp": time.time(),
            }),
            encoding="utf-8",
        )
    except Exception:
        pass


class MLXBackend:
    """MLX-based LLM backend for Apple Silicon.

    Implements LLMBackendProtocol.
    Uses mlx-lm for model loading and text generation.
    """

    def __init__(self) -> None:
        self._model: object | None = None
        self._tokenizer: object | None = None
        self._model_id: str = ""
        self._context_window: int = 8192

    @property
    def is_loaded(self) -> bool:
        return self._model is not None

    @property
    def model_id(self) -> str:
        return self._model_id

    def load(self, decision: RuntimeDecision) -> None:
        """Load the model specified by RuntimeDecision.

        If a different model is already loaded, unloads it first.
        """
        repo_id = _resolve_model_id(decision.model_id)

        if self._model is not None and self._model_id == repo_id:
            logger.info("Model %s already loaded, skipping.", repo_id)
            return

        if self._model is not None:
            self.unload()

        logger.info("Loading MLX model: %s", repo_id)
        t0 = time.perf_counter()

        from mlx_lm import load as mlx_load
        self._model, self._tokenizer = mlx_load(repo_id)

        elapsed = time.perf_counter() - t0
        self._model_id = repo_id
        self._context_window = decision.context_window
        logger.info("Model loaded in %.1fs: %s", elapsed, repo_id)

    def unload(self) -> None:
        """Unload the current model and release memory."""
        if self._model is None:
            return

        model_id = self._model_id
        logger.info("Unloading MLX model: %s", model_id)

        self._model = None
        self._tokenizer = None
        self._model_id = ""

        # Force Metal memory reclaim
        try:
            import mlx.core as mx
            mx.metal.clear_cache()
        except Exception:
            pass

        logger.info("Model unloaded: %s", model_id)

    def generate(self, prompt: str, context: str, intent: str) -> str:
        """Generate a response given prompt, context, and intent.

        Args:
            prompt: User query text.
            context: Assembled retrieved context string.
            intent: Intent classification.

        Returns:
            Generated response text.

        Raises:
            RuntimeError: If no model is loaded.
        """
        if self._model is None or self._tokenizer is None:
            raise RuntimeError("No model loaded. Call load() first.")

        from mlx_lm import generate as mlx_generate
        from mlx_lm.sample_utils import make_sampler

        system_message = (
            "당신은 JARVIS입니다. 사용자의 로컬 워크스페이스 AI 어시스턴트입니다. "
            "제공된 증거를 기반으로 정확하고 간결하게 답변하세요. "
            "증거가 없는 내용은 추측하지 마세요. "
            "표 형식 데이터에서는 헤더(첫 행)와 데이터 행의 열 위치를 정확히 대응시켜 답변하세요. "
            "| 구분자로 나뉜 데이터에서 n번째 열은 헤더의 n번째 열에 해당합니다."
        )

        if context.strip():
            system_message += f"\n\n참고 증거:\n{context}"

        messages = [
            {"role": "system", "content": system_message},
            {"role": "user", "content": prompt},
        ]

        formatted_prompt = self._tokenizer.apply_chat_template(
            messages, add_generation_prompt=True
        )

        # Dynamic max_tokens: use remaining context window after prompt
        prompt_tokens = len(formatted_prompt) if isinstance(formatted_prompt, list) else len(self._tokenizer.encode(formatted_prompt))
        _RESERVE = 256
        max_tokens = max(256, self._context_window - prompt_tokens - _RESERVE)
        logger.debug(
            "Dynamic token budget: context=%d, prompt=%d, reserve=%d, max_tokens=%d",
            self._context_window, prompt_tokens, _RESERVE, max_tokens,
        )

        sampler = make_sampler(
            0.7,
            0.9,
            0.0,
            1,
        )

        t0 = time.perf_counter()
        response = mlx_generate(
            self._model,
            self._tokenizer,
            prompt=formatted_prompt,
            max_tokens=max_tokens,
            sampler=sampler,
        )
        elapsed_ms = (time.perf_counter() - t0) * 1000

        logger.info(
            "Generated %d chars in %.0fms (model=%s, intent=%s)",
            len(response), elapsed_ms, self._model_id, intent,
        )

        return response


# Runtime-checkable verification
assert isinstance(MLXBackend(), LLMBackendProtocol)
