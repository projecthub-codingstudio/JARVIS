"""MLXRuntime — bridges LLMBackendProtocol to LLMGeneratorProtocol.

Wraps a real LLMBackendProtocol backend (MLXBackend or LlamaCppBackend)
to satisfy the Orchestrator's LLMGeneratorProtocol interface.
Falls back to stub behavior when no backend is provided.

Per Spec Task 1.3: enforces max_context_tokens budget when assembling
evidence context for the LLM.
"""

from __future__ import annotations

import re
import time
from collections.abc import Iterator
from pathlib import Path
from typing import TYPE_CHECKING

from jarvis.contracts import (
    AnswerDraft,
    LLMBackendProtocol,
    LLMGeneratorProtocol,
    VerifiedEvidenceSet,
)
from jarvis.observability.metrics import MetricName, MetricsCollector
from jarvis.retrieval.citation_verifier import CitationVerifier

if TYPE_CHECKING:
    from jarvis.contracts import ConversationTurn

_THINK_RE = re.compile(r"<think>.*?</think>\s*|<thought>.*?</thought>\s*", re.DOTALL)
_CLASS_QUERY_RE = re.compile(r"(?:\bclass\b|클래스)\s+([A-Za-z_][A-Za-z0-9_]*)", re.IGNORECASE)
_IDENTIFIER_RE = re.compile(r"\b[A-Za-z_][A-Za-z0-9_]{2,}\b")


def strip_think_tags(text: str) -> str:
    """Remove <think>...</think> and <thought>...</thought> blocks from LLM output."""
    return _THINK_RE.sub("", text).strip()


# Approximate token count: 1 Korean char ≈ 1 token, 1 English word ≈ 1 token
# Conservative estimate: 4 chars per token average (mixed Korean/English)
_CHARS_PER_TOKEN = 4

# Default context budget per Spec: 8K context window, reserve ~2K for system+answer
_MAX_CONTEXT_TOKENS = 4096
_MAX_CONTEXT_CHARS = _MAX_CONTEXT_TOKENS * _CHARS_PER_TOKEN

# Conversation history budget: ~800 tokens for 3 turns (Korean-heavy)
_MAX_HISTORY_TOKENS = 800
_MAX_HISTORY_CHARS = _MAX_HISTORY_TOKENS * _CHARS_PER_TOKEN


def _estimate_tokens(text: str) -> int:
    """Rough token estimate for mixed Korean/English text."""
    return len(text) // _CHARS_PER_TOKEN


def _extract_requested_identifier(prompt: str, evidence: VerifiedEvidenceSet) -> str:
    direct_match = _CLASS_QUERY_RE.search(prompt)
    if direct_match:
        return direct_match.group(1)

    identifiers = _IDENTIFIER_RE.findall(prompt)
    evidence_text = " ".join(item.text for item in evidence.items[:3])
    for identifier in identifiers:
        if re.search(rf"\bclass\s+{re.escape(identifier)}\b", evidence_text, re.IGNORECASE):
            return identifier
    return ""


def _build_stub_grounded_response(prompt: str, evidence: VerifiedEvidenceSet) -> str:
    sources = [item.source_path or item.document_id for item in evidence.items[:3]]
    unique_sources = [source for index, source in enumerate(sources) if source and source not in sources[:index]]
    primary_source = unique_sources[0] if unique_sources else "확인된 소스"
    citation_labels = ", ".join(item.citation.label for item in evidence.items[:3])
    head = _extract_best_stub_snippet(prompt, evidence)
    identifier = _extract_requested_identifier(prompt, evidence)

    if re.search(r"(?:\bclass\b|클래스)", prompt, re.IGNORECASE):
        if identifier:
            intro = f"확인된 근거 기준으로 `{identifier}` 클래스는 [{primary_source}]에 정의되어 있습니다."
        else:
            intro = f"확인된 근거 기준으로 요청하신 클래스는 [{primary_source}]에서 확인됩니다."
        body = (
            "현재 모델 생성 경로가 비활성이라 코드 근거를 그대로 요약합니다. "
            f"첫 번째 확인 구간은 다음과 같습니다: {head}"
        )
        return f"{intro}\n{body}\n근거: {citation_labels}"

    intro = f"확인된 근거는 [{primary_source}]에 있습니다."
    body = f"현재 모델 생성 경로가 비활성이라 검색 근거를 그대로 요약합니다: {head}"
    return f"{intro}\n{body}\n근거: {citation_labels}"


def _extract_best_stub_snippet(prompt: str, evidence: VerifiedEvidenceSet) -> str:
    if not evidence.items:
        return ""
    primary_source = evidence.items[0].source_path or ""
    wants_class = bool(re.search(r"(?:\bclass\b|클래스)", prompt, re.IGNORECASE))
    wants_function = bool(re.search(r"(?:\bfunction\b|\bmethod\b|\bdef\b|함수|메서드|메소드)", prompt, re.IGNORECASE))
    identifier = _extract_requested_identifier(prompt, evidence)

    if primary_source:
        extracted = _extract_source_snippet(
            source_path=primary_source,
            identifier=identifier,
            wants_class=wants_class,
            wants_function=wants_function,
        )
        if extracted:
            return extracted

    head = evidence.items[0].text.strip()
    head = re.sub(r"\s+", " ", head)
    return head[:220].rstrip()


def _extract_source_snippet(
    *,
    source_path: str,
    identifier: str,
    wants_class: bool,
    wants_function: bool,
) -> str:
    path = Path(source_path)
    if not path.exists() or not path.is_file():
        return ""
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""

    candidates: list[str] = []
    if identifier:
        candidates.append(identifier)
    stem = path.stem
    if stem:
        candidates.append(stem)
        candidates.append(stem.title())
        candidates.append(stem.capitalize())

    for candidate in dict.fromkeys(value for value in candidates if value):
        if wants_class:
            match = re.search(rf"^\s*class\s+{re.escape(candidate)}\b.*$", text, re.MULTILINE)
            if match:
                return _window_from_match(text, match.start())
        if wants_function:
            match = re.search(rf"^\s*def\s+{re.escape(candidate)}\b.*$", text, re.MULTILINE)
            if match:
                return _window_from_match(text, match.start())

    if wants_class:
        match = re.search(r"^\s*class\s+[A-Za-z_][A-Za-z0-9_]*\b.*$", text, re.MULTILINE)
        if match:
            return _window_from_match(text, match.start())
    if wants_function:
        match = re.search(r"^\s*def\s+[A-Za-z_][A-Za-z0-9_]*\b.*$", text, re.MULTILINE)
        if match:
            return _window_from_match(text, match.start())

    return ""


def _window_from_match(text: str, offset: int, *, max_lines: int = 18, max_chars: int = 320) -> str:
    lines = text.splitlines()
    consumed = 0
    start_line = 0
    for index, line in enumerate(lines):
        consumed += len(line) + 1
        if consumed > offset:
            start_line = index
            break
    snippet = "\n".join(lines[start_line:start_line + max_lines]).strip()
    snippet = re.sub(r"\s+", " ", snippet)
    return snippet[:max_chars].rstrip()


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
        metrics: MetricsCollector | None = None,
        status_detail: str = "",
    ) -> None:
        self._backend = backend
        self._model_id = model_id
        self._max_context_chars = max_context_chars
        self._metrics = metrics
        self._citation_verifier = CitationVerifier()
        self._context_assembler = None
        self._status_detail = status_detail

    def _post_verify(self, answer: AnswerDraft) -> None:
        """Run citation verification after answer is yielded (post-verification).

        Updates answer.verification_warnings in place. This runs after
        the AnswerDraft has been yielded to the REPL, so the user sees
        the answer immediately without waiting for verification.
        """
        try:
            warnings = self._citation_verifier.verify(answer.content, answer.evidence)
            answer.verification_warnings = warnings
        except Exception:
            pass  # Verification failure should not affect the answer

    def _assemble_context(self, evidence: VerifiedEvidenceSet, query: str = "") -> str:
        """Assemble evidence via ContextAssembler (Pipeline Step 5)."""
        if self._context_assembler is None:
            from jarvis.retrieval.context_assembler import ContextAssembler
            self._context_assembler = ContextAssembler(
                max_context_chars=self._max_context_chars,
            )
        assembled = self._context_assembler.assemble(evidence, query)
        return assembled.render_for_llm()

    @property
    def model_id(self) -> str:
        """Expose the active backend model id for observability."""
        if self._backend is not None and hasattr(self._backend, "model_id"):
            return str(getattr(self._backend, "model_id"))
        return self._model_id

    @property
    def status_detail(self) -> str:
        """Return the backend/runtime detail for observability."""
        if self._backend is not None and hasattr(self._backend, "status_detail"):
            return str(getattr(self._backend, "status_detail"))
        return self._status_detail

    def unload(self) -> None:
        """Unload the active backend model if the backend exposes lifecycle hooks."""
        if self._backend is not None and hasattr(self._backend, "unload"):
            try:
                self._backend.unload()
            except Exception:
                pass

    def _assemble_history(self, recent_turns: list[ConversationTurn] | None) -> str:
        """Assemble recent conversation turns into a history string.

        Sliding window: includes up to 3 recent turns, capped at
        _MAX_HISTORY_CHARS to preserve token budget for evidence.
        """
        if not recent_turns:
            return ""

        parts: list[str] = []
        total_chars = 0

        for turn in recent_turns:
            user_part = f"사용자: {turn.user_input}"
            assistant_part = f"JARVIS: {turn.assistant_output or ''}"
            # Truncate long assistant responses
            if len(assistant_part) > 200:
                assistant_part = assistant_part[:200] + "..."
            entry = f"{user_part}\n{assistant_part}"

            if total_chars + len(entry) > _MAX_HISTORY_CHARS:
                break
            parts.append(entry)
            total_chars += len(entry)

        return "\n".join(parts)

    def generate(
        self,
        prompt: str,
        evidence: VerifiedEvidenceSet,
        *,
        recent_turns: list[ConversationTurn] | None = None,
    ) -> AnswerDraft:
        """Generate a grounded answer from evidence with conversation history.

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
        context = self._assemble_context(evidence, prompt)

        # Assemble conversation history (sliding window, 3 turns)
        history = self._assemble_history(recent_turns)
        if history:
            context = f"[이전 대화]\n{history}\n\n[참고 증거]\n{context}"

        # Real backend path
        if self._backend is not None:
            t0 = time.perf_counter()
            raw_text = self._backend.generate(prompt, context, "read_only")
            response_text = strip_think_tags(raw_text)
            elapsed_ms = (time.perf_counter() - t0) * 1000
            if self._metrics is not None:
                self._metrics.record(
                    MetricName.TTFT_MS,
                    elapsed_ms,
                    tags={"stage": "generation"},
                )
            warnings = self._citation_verifier.verify(response_text, evidence)

            return AnswerDraft(
                content=response_text,
                evidence=evidence,
                model_id=self._backend.model_id if hasattr(self._backend, "model_id") else self._model_id,
                generation_time_ms=elapsed_ms,
                verification_warnings=warnings,
            )

        # Stub fallback
        return AnswerDraft(
            content=_build_stub_grounded_response(prompt, evidence),
            evidence=evidence,
            model_id=self._model_id,
            generation_time_ms=1.0,
            verification_warnings=(),
        )

    def generate_stream(
        self,
        prompt: str,
        evidence: VerifiedEvidenceSet,
        *,
        recent_turns: list[ConversationTurn] | None = None,
    ) -> Iterator[str | AnswerDraft]:
        """Stream tokens from the LLM, filtering think tags mid-stream.

        Yields:
            str: Individual tokens for real-time display.
            AnswerDraft: Final sentinel containing the complete response
                         (always the last item yielded).
        """
        if evidence.is_empty:
            yield AnswerDraft(
                content="충분한 증거가 없어 답변을 생성할 수 없습니다.",
                evidence=evidence,
                model_id=self._model_id,
            )
            return

        context = self._assemble_context(evidence, prompt)
        history = self._assemble_history(recent_turns)
        if history:
            context = f"[이전 대화]\n{history}\n\n[참고 증거]\n{context}"

        # Check if backend supports streaming
        if self._backend is not None and hasattr(self._backend, "generate_stream"):
            t0 = time.perf_counter()
            full_tokens: list[str] = []
            in_think = False
            think_buffer: list[str] = []

            for token in self._backend.generate_stream(prompt, context, "read_only"):
                full_tokens.append(token)

                # Think-tag state machine
                combined = "".join(think_buffer) + token if think_buffer else token

                if not in_think:
                    if "<think>" in combined or "<thought>" in combined:
                        # Entered think block — emit text before tag
                        tag = "<think>" if "<think>" in combined else "<thought>"
                        before = combined.split(tag, 1)[0]
                        if before:
                            yield before
                        in_think = True
                        think_buffer = []
                        continue
                    # Check for partial tag at end (e.g., "<thi")
                    if "<" in token and not token.endswith(">"):
                        think_buffer.append(token)
                        continue
                    if think_buffer:
                        # False alarm — flush buffer
                        for buf_token in think_buffer:
                            yield buf_token
                        think_buffer = []
                    yield token
                else:
                    # Inside think block — suppress output
                    if "</think>" in combined or "</thought>" in combined:
                        in_think = False
                        after = combined.split("</think>", 1)[1]
                        think_buffer = []
                        if after.strip():
                            yield after
                    # else: keep suppressing

            # Flush any remaining buffer
            if think_buffer and not in_think:
                for buf_token in think_buffer:
                    yield buf_token

            elapsed_ms = (time.perf_counter() - t0) * 1000
            raw_text = "".join(full_tokens)
            response_text = strip_think_tags(raw_text)

            if self._metrics is not None:
                self._metrics.record(
                    MetricName.TTFT_MS, elapsed_ms,
                    tags={"stage": "generation"},
                )
            # Yield AnswerDraft immediately without verification (post-verification)
            answer = AnswerDraft(
                content=response_text,
                evidence=evidence,
                model_id=self._backend.model_id if hasattr(self._backend, "model_id") else self._model_id,
                generation_time_ms=elapsed_ms,
                verification_warnings=(),
            )
            yield answer

            # Run verification asynchronously — updates answer in place
            self._post_verify(answer)
        else:
            # No streaming support — fall back to non-streaming generate
            answer = self.generate(prompt, evidence, recent_turns=recent_turns)
            for chunk in re.split(r"(\n+)", answer.content):
                if chunk:
                    yield chunk
            yield answer
