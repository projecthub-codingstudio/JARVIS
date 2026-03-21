"""llama.cpp Backend — compatibility backend via Ollama REST API.

Implements LLMBackendProtocol per Implementation Spec Section 2.2, Task 0.3.
Fallback inference backend when MLX is unavailable or for specific models.
Communicates with Ollama server at localhost:11434.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import time
import urllib.request
import urllib.error
from pathlib import Path

from jarvis.contracts import LLMBackendProtocol, RuntimeDecision

logger = logging.getLogger(__name__)

_OLLAMA_BASE = "http://localhost:11434"
_COMMON_BINARY_DIRS = (
    Path("/opt/homebrew/bin"),
    Path("/usr/local/bin"),
    Path("/usr/bin"),
)

# Model ID mapping: short alias -> Ollama model tag
_MODEL_ALIASES: dict[str, str] = {
    "qwen3-14b": "qwen3:14b",
    "qwen3-30b-a3b": "qwen3:30b-a3b",
    "kanana-30b-a3b": "qwen3:30b-a3b",
    "exaone-deep-7.8b": "exaone3.5:7.8b",
    "exaone-7.8b": "exaone3.5:7.8b",
    "llama3.2": "llama3.2:latest",
}


def _resolve_model_id(model_id: str) -> str:
    """Resolve short alias to Ollama model tag."""
    return _MODEL_ALIASES.get(model_id, model_id)


class LlamaCppBackend:
    """llama.cpp-compatible backend via Ollama REST API.

    Implements LLMBackendProtocol.
    Uses Ollama's /api/generate endpoint for inference.
    """

    def __init__(self, *, base_url: str = _OLLAMA_BASE) -> None:
        self._base_url = base_url
        self._model_id: str = ""
        self._context_window: int = 8192
        self._loaded: bool = False
        self._status_detail: str = "not loaded"

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    @property
    def model_id(self) -> str:
        return self._model_id

    @property
    def status_detail(self) -> str:
        return self._status_detail

    def load(self, decision: RuntimeDecision) -> None:
        """Load (warm up) the model in Ollama.

        Ollama manages model lifecycle, so 'load' verifies availability
        and optionally pre-warms the model.
        """
        model_tag = _resolve_model_id(decision.model_id)

        if self._loaded and self._model_id == model_tag:
            logger.info("Model %s already loaded in Ollama.", model_tag)
            return

        server_ready, detail = self._ensure_server_ready()
        if not server_ready:
            self._status_detail = detail
            raise RuntimeError(detail)
        if not self._check_model_available(model_tag):
            self._status_detail = (
                f"Ollama server is reachable, but model '{model_tag}' is not available. "
                f"Run: ollama pull {model_tag}"
            )
            raise RuntimeError(self._status_detail)

        self._model_id = model_tag
        self._context_window = decision.context_window
        self._loaded = True
        self._status_detail = f"OK ({model_tag})"
        logger.info("Ollama backend ready with model: %s", model_tag)

    def unload(self) -> None:
        """Mark model as unloaded. Ollama manages actual memory."""
        if not self._loaded:
            return

        model_id = self._model_id
        # Send keep_alive=0 to request Ollama unload the model
        try:
            payload = json.dumps({
                "model": self._model_id,
                "keep_alive": 0,
            }).encode()
            req = urllib.request.Request(
                f"{self._base_url}/api/generate",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            urllib.request.urlopen(req, timeout=10)
        except Exception:
            pass

        self._model_id = ""
        self._loaded = False
        logger.info("Ollama model unloaded: %s", model_id)

    def generate(self, prompt: str, context: str, intent: str) -> str:
        """Generate a response via Ollama API.

        Args:
            prompt: User query text.
            context: Assembled retrieved context string.
            intent: Intent classification.

        Returns:
            Generated response text.

        Raises:
            RuntimeError: If no model is loaded or Ollama is unavailable.
        """
        if not self._loaded:
            raise RuntimeError("No model loaded. Call load() first.")

        system_message = (
            "당신은 JARVIS입니다. 사용자의 로컬 워크스페이스 AI 어시스턴트입니다. "
            "제공된 증거를 기반으로 정확하고 간결하게 답변하세요. "
            "증거가 없는 내용은 추측하지 마세요. "
            "표 형식 데이터에서는 헤더(첫 행)와 데이터 행의 열 위치를 정확히 대응시켜 답변하세요. "
            "| 구분자로 나뉜 데이터에서 n번째 열은 헤더의 n번째 열에 해당합니다."
        )

        if context.strip():
            system_message += f"\n\n참고 증거:\n{context}"

        # Estimate prompt tokens: Korean ~1 char/token, English ~4 chars/token
        # Use conservative 1.5 chars/token for mixed content
        estimated_prompt_tokens = int(len(system_message + prompt) / 1.5)
        _RESERVE = 256
        num_predict = max(256, self._context_window - estimated_prompt_tokens - _RESERVE)
        logger.debug(
            "Dynamic token budget: context=%d, est_prompt=%d, num_predict=%d",
            self._context_window, estimated_prompt_tokens, num_predict,
        )

        payload = json.dumps({
            "model": self._model_id,
            "system": system_message,
            "prompt": prompt,
            "stream": False,
            "think": False,
            "options": {
                "num_ctx": self._context_window,
                "temperature": 0.7,
                "top_p": 0.9,
                "num_predict": num_predict,
            },
        }).encode()

        req = urllib.request.Request(
            f"{self._base_url}/api/generate",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        t0 = time.perf_counter()
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                result = json.loads(resp.read().decode())
        except urllib.error.URLError as e:
            raise RuntimeError(f"Ollama API error: {e}") from e

        elapsed_ms = (time.perf_counter() - t0) * 1000
        response_text = result.get("response", "")

        logger.info(
            "Generated %d chars in %.0fms (model=%s, intent=%s)",
            len(response_text), elapsed_ms, self._model_id, intent,
        )

        return response_text

    def _check_model_available(self, model_tag: str) -> bool:
        """Check if model exists in Ollama."""
        try:
            req = urllib.request.Request(
                f"{self._base_url}/api/tags",
                method="GET",
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode())
                models = [m["name"] for m in data.get("models", [])]
                return model_tag in models
        except Exception:
            return False

    def _ensure_server_ready(self) -> tuple[bool, str]:
        if self._server_reachable():
            return True, "Ollama server reachable"

        binary = self._resolve_binary()
        if binary is None:
            return False, "Ollama binary not found. Install Ollama or set PATH correctly."

        try:
            process = subprocess.Popen(
                [binary, "serve"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
                start_new_session=True,
                env=os.environ.copy(),
            )
        except Exception as exc:
            return False, f"Ollama server failed to start: {exc}"

        for _ in range(20):
            time.sleep(0.25)
            if self._server_reachable():
                return True, "Ollama server started"
            if process.poll() is not None:
                return False, "Ollama server process exited during startup"

        return False, "Ollama server did not become ready on localhost:11434"

    def _server_reachable(self) -> bool:
        try:
            req = urllib.request.Request(f"{self._base_url}/api/tags", method="GET")
            with urllib.request.urlopen(req, timeout=2):
                return True
        except Exception:
            return False

    def _resolve_binary(self) -> str | None:
        env_binary = os.getenv("OLLAMA_BINARY")
        if env_binary:
            env_path = Path(env_binary).expanduser()
            if env_path.exists():
                return str(env_path.resolve())

        resolved = shutil.which("ollama")
        if resolved is not None:
            return resolved

        for directory in _COMMON_BINARY_DIRS:
            candidate = directory / "ollama"
            if candidate.exists():
                return str(candidate)
        return None


# Runtime-checkable verification
assert isinstance(LlamaCppBackend(), LLMBackendProtocol)
