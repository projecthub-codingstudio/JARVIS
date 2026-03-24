"""Data-driven vocabulary biasing for STT."""

from __future__ import annotations

from pathlib import Path

from jarvis.identifier_restoration import build_identifier_lexicon

_MAX_TERMS = 120
_MAX_PROMPT_CHARS = 900


def build_vocabulary_hint(knowledge_base_path: Path | None) -> str:
    """Extract a compact STT vocabulary hint from local indexed source files."""
    terms: list[str] = []
    seen: set[str] = set()
    for entry in build_identifier_lexicon(knowledge_base_path):
        _add_term(entry.canonical, terms, seen)
        for token in entry.tokens:
            _add_term(token, terms, seen)
        if len(terms) >= _MAX_TERMS:
            break

    if not terms:
        return ""

    prompt = "Technical vocabulary: " + ", ".join(terms[:_MAX_TERMS])
    return prompt[:_MAX_PROMPT_CHARS]


def _add_term(term: str, terms: list[str], seen: set[str]) -> None:
    cleaned = term.strip()
    lowered = cleaned.lower()
    if not cleaned or lowered in seen:
        return
    if len(cleaned) < 3:
        return
    if not any(ch.isalpha() for ch in cleaned):
        return
    seen.add(lowered)
    terms.append(cleaned)
