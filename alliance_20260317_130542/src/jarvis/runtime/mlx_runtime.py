"""MLXRuntime — bridges LLMBackendProtocol to LLMGeneratorProtocol.

Wraps a real LLMBackendProtocol backend (MLXBackend or LlamaCppBackend)
to satisfy the Orchestrator's LLMGeneratorProtocol interface.
Falls back to stub behavior when no backend is provided.

Per Spec Task 1.3: enforces max_context_tokens budget when assembling
evidence context for the LLM.
"""

from __future__ import annotations

import time

from jarvis.contracts import (
    AnswerDraft,
    LLMBackendProtocol,
    LLMGeneratorProtocol,
    VerifiedEvidenceSet,
)

# Approximate token count: 1 Korean char ≈ 1 token, 1 English word ≈ 1 token
# Conservative estimate: 4 chars per token average (mixed Korean/English)
_CHARS_PER_TOKEN = 4

# Default context budget per Spec: 8K context window, reserve ~2K for system+answer
_MAX_CONTEXT_TOKENS = 4096
_MAX_CONTEXT_CHARS = _MAX_CONTEXT_TOKENS * _CHARS_PER_TOKEN


def _estimate_tokens(text: str) -> int:
    """Rough token estimate for mixed Korean/English text."""
    return len(text) // _CHARS_PER_TOKEN


class MLXRuntime:
    """LLM generation runtime bridging Backend → Generator protocols.

    Implements LLMGeneratorProtocol for Orchestrator compatibility.
    Delegates actual inference to an LLMBackendProtocol implementation.
    Enforces token budget when assembling evidence context.
    """

    def __init__(
        self,
        *,
        backend: LLMBackendProtocol | None = None,
        model_id: str = "default-14b-q4",
        max_context_chars: int = _MAX_CONTEXT_CHARS,
    ) -> None:
        self._backend = backend
        self._model_id = model_id
        self._max_context_chars = max_context_chars

    def _assemble_context(self, evidence: VerifiedEvidenceSet) -> str:
        """Assemble evidence into context string, respecting token budget.

        Evidence items are added in order (highest relevance first)
        until the budget is exhausted. Per Spec Task 1.3.
        """
        context_parts: list[str] = []
        total_chars = 0

        for item in evidence.items:
            label = item.citation.label
            source = f" ({item.source_path})" if item.source_path else ""
            heading = f" [{item.heading_path}]" if item.heading_path else ""
            part = f"{label}{source}{heading}: {item.text}"

            if total_chars + len(part) > self._max_context_chars:
                # Budget exhausted — truncate this part or stop
                remaining = self._max_context_chars - total_chars
                if remaining > 100:  # Only include if meaningful portion fits
                    context_parts.append(part[:remaining] + "...")
                break

            context_parts.append(part)
            total_chars += len(part)

        return "\n".join(context_parts)

    def generate(self, prompt: str, evidence: VerifiedEvidenceSet) -> AnswerDraft:
        """Generate a grounded answer from evidence.

        If a real backend is connected, delegates to it.
        Otherwise falls back to stub behavior.
        """
        if evidence.is_empty:
            return AnswerDraft(
                content="충분한 증거가 없어 답변을 생성할 수 없습니다.",
                evidence=evidence,
                model_id=self._model_id,
            )

        # Assemble evidence with token budget enforcement
        context = self._assemble_context(evidence)

        # Real backend path
        if self._backend is not None:
            t0 = time.perf_counter()
            response_text = self._backend.generate(prompt, context, "read_only")
            elapsed_ms = (time.perf_counter() - t0) * 1000

            return AnswerDraft(
                content=response_text,
                evidence=evidence,
                model_id=self._backend.model_id if hasattr(self._backend, "model_id") else self._model_id,
                generation_time_ms=elapsed_ms,
            )

        # Stub fallback
        citations = ", ".join(item.citation.label for item in evidence.items)
        return AnswerDraft(
            content=(
                f"[stub:{self._model_id}] 질문 '{prompt}'에 대해 "
                f"증거 {citations}을(를) 기반으로 답변합니다. "
                f"(Phase 1에서 실제 LLM이 연결되면 자연어 답변이 생성됩니다)"
            ),
            evidence=evidence,
            model_id=self._model_id,
            generation_time_ms=1.0,
        )
