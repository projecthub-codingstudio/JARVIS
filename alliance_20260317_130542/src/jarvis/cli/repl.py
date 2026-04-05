"""REPL — read-eval-print loop for interactive JARVIS sessions.

Provides the text-based CLI interface for Phase 1 (push-to-talk
wake word deferred to Phase 2).

Per Spec Task 1.4/1.5 and Section 3.2/3.5:
  Cited render with file_path, line_start/line_end,
  retrieval_score, source_type, and quote.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

from jarvis.contracts import AnswerDraft, ConversationTurn, EvidenceItem
from jarvis.core.orchestrator import Orchestrator
from jarvis.retrieval.evidence_builder import MIN_RELEVANCE_SCORE

# Max quote length for display
_MAX_QUOTE_CHARS = 120

# Regex to match inline full paths like (/Users/.../file.ext) or (path/to/file.ext)
_INLINE_PATH_RE = re.compile(
    r"\((/[^\)]{20,})\)"
)


def _strip_inline_paths(text: str) -> str:
    """Replace inline full paths with just the filename for cleaner output.

    Transforms: [1] (/Users/foo/bar/file.xlsx) → [1] file.xlsx
    """
    def _replace(m: re.Match) -> str:
        full_path = m.group(1)
        try:
            return Path(full_path).name
        except Exception:
            return m.group(0)
    return _INLINE_PATH_RE.sub(_replace, text)


def _detect_source_type(path: str) -> str:
    """Detect source_type per Spec: 'document' or 'code'."""
    code_exts = {".py", ".ts", ".tsx", ".js", ".jsx", ".yaml", ".yml", ".json"}
    try:
        suffix = Path(path).suffix.lower()
        return "code" if suffix in code_exts else "document"
    except Exception:
        return "document"


def _shorten_path(source: str) -> str:
    """Shorten path for display, keeping parent/filename."""
    try:
        p = Path(source)
        return p.name
    except Exception:
        return source


def _make_quote(item: EvidenceItem) -> str:
    """Extract a short quote from evidence text."""
    text = item.text.strip()
    # Take first meaningful line
    for line in text.split("\n"):
        line = line.strip()
        if len(line) > 20:
            if len(line) > _MAX_QUOTE_CHARS:
                return line[:_MAX_QUOTE_CHARS] + "..."
            return line
    # Fallback: first N chars
    if len(text) > _MAX_QUOTE_CHARS:
        return text[:_MAX_QUOTE_CHARS] + "..."
    return text


class JarvisREPL:
    """Interactive read-eval-print loop for JARVIS."""

    def __init__(
        self,
        orchestrator: Orchestrator,
        *,
        prompt: str = "jarvis> ",
    ) -> None:
        self._orchestrator = orchestrator
        self._prompt = prompt
        self._running = False

    def start(self) -> None:
        """Start the REPL loop. Ctrl+C or 'exit'/'quit' to stop."""
        self._running = True
        print("   Type your question, or 'exit' to quit.\n")

        while self._running:
            try:
                user_input = input(self._prompt).strip()
            except (EOFError, KeyboardInterrupt):
                print("\n👋 안녕히 가세요!")
                break

            if not user_input:
                continue
            if user_input.lower() in ("exit", "quit", "q", "종료"):
                print("👋 안녕히 가세요!")
                break

            # Use streaming if available, fall back to non-streaming
            if hasattr(self._orchestrator, "handle_turn_stream"):
                self._handle_streaming(user_input)
            else:
                turn = self._orchestrator.handle_turn(user_input)
                answer = self._orchestrator.last_answer
                self._display_response(
                    turn.assistant_output or "(응답 없음)",
                    answer=answer,
                )

    def stop(self) -> None:
        """Gracefully stop the REPL loop."""
        self._running = False

    def _handle_streaming(self, user_input: str) -> None:
        """Handle a turn with real-time streaming token display."""
        sys.stdout.write("\n  ")
        sys.stdout.flush()
        turn: ConversationTurn | None = None
        token_count = 0

        for item in self._orchestrator.handle_turn_stream(user_input):
            if isinstance(item, str):
                # Real-time token display with inline path stripping
                clean = _strip_inline_paths(item)
                sys.stdout.write(clean)
                sys.stdout.flush()
                token_count += 1
            else:
                # ConversationTurn sentinel — stream complete
                turn = item

        if token_count > 0:
            sys.stdout.write("\n")
            sys.stdout.flush()

        if turn is not None and token_count == 0:
            # Non-streaming response (safety block, no evidence, etc.)
            clean = _strip_inline_paths(turn.assistant_output or "(응답 없음)")
            print(f"  {clean}")

        answer = self._orchestrator.last_answer
        if answer is not None and answer.verification_warnings:
            print("\n  ⚠  검증 경고")
            for warning in answer.verification_warnings[:3]:
                print(f"     {warning}")

        if answer is not None and not answer.evidence.is_empty:
            self._display_citations(answer)

        print()

    def _display_response(
        self, response: str, *, answer: AnswerDraft | None = None
    ) -> None:
        """Display response with citations per Spec Task 1.4/1.5."""
        # Strip any inline full paths from LLM output for cleaner display
        clean_response = _strip_inline_paths(response)
        print(f"\n  {clean_response}")

        if answer is not None and answer.verification_warnings:
            print("\n  ⚠  검증 경고")
            for warning in answer.verification_warnings[:3]:
                print(f"     {warning}")

        if answer is not None and answer.verification_warnings:
            print("\n  ─── 검증 경고 ───")
            for warning in answer.verification_warnings[:3]:
                print(f"  - {warning}")

        if answer is not None and not answer.evidence.is_empty:
            self._display_citations(answer)

        print()

    def _display_citations(self, answer: AnswerDraft) -> None:
        """Render only the top relevant citations per Spec Section 3.2/3.5.

        Shows up to 3 unique source files, deduplicated and sorted
        by relevance score. Only includes citations actually relevant
        to the answer.
        """
        # Only show citations that the answer actually references
        # Check if the answer text mentions the citation label [1], [2], etc.
        answer_text = answer.content

        # Deduplicate by source file, keep highest scoring per file
        # Only include if the citation label appears in the answer text
        # or if the evidence text content is reflected in the answer
        best_per_file: dict[str, EvidenceItem] = {}
        for item in answer.evidence.items:
            if item.relevance_score < MIN_RELEVANCE_SCORE:
                continue
            # Check if this citation's label is referenced in the answer
            label_referenced = item.citation.label in answer_text

            # Check if key content from this evidence appears in the answer
            evidence_words = set(item.text.split()[:10])
            answer_words = set(answer_text.split())
            content_overlap = len(evidence_words & answer_words) >= 3

            if not label_referenced and not content_overlap:
                continue

            source = item.source_path or item.document_id
            filename = _shorten_path(source)
            if filename not in best_per_file or item.relevance_score > best_per_file[filename].relevance_score:
                best_per_file[filename] = item

        # If no citations matched by content, show top 1 by score as fallback
        if not best_per_file and answer.evidence.items:
            top_item = max(answer.evidence.items, key=lambda x: x.relevance_score)
            if top_item.relevance_score >= MIN_RELEVANCE_SCORE:
                source = top_item.source_path or top_item.document_id
                best_per_file[_shorten_path(source)] = top_item

        top_items = sorted(best_per_file.values(), key=lambda x: x.relevance_score, reverse=True)[:3]

        if not top_items:
            return

        print()
        print("  ╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌")
        print("   출처")
        print("  ╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌")
        for item in top_items:
            source = item.source_path or item.document_id
            filename = _shorten_path(source)
            source_type = _detect_source_type(source)

            # Warning if stale/missing
            warning = ""
            if item.citation.state.needs_warning:
                state_labels = {
                    "STALE": " ⚠ 변경됨",
                    "MISSING": " ⚠ 삭제됨",
                    "ACCESS_LOST": " ⚠ 접근불가",
                }
                label = state_labels.get(item.citation.state.value, item.citation.state.value)
                warning = label

            label = item.citation.label
            print(f"   {label} {filename}{warning}")

            # Quote in subdued style (indented further)
            quote = _make_quote(item)
            if quote:
                print(f"      \033[2m{quote}\033[0m")
