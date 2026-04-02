"""Data-driven vocabulary biasing for STT."""

from __future__ import annotations

import re
import sqlite3
import unicodedata
from pathlib import Path

from jarvis.identifier_restoration import build_identifier_lexicon
from jarvis.runtime_paths import resolve_menubar_data_dir

_MAX_TERMS = 120
_MAX_PROMPT_CHARS = 900
_TOKEN_RE = re.compile(r"[0-9A-Za-z가-힣+/_\.-]+")
_PATH_TOKEN_RE = re.compile(r"[A-Za-z가-힣]+")
_MAX_CHUNK_ROWS = 120
_KOREAN_RE = re.compile(r"[가-힣]")
_GLOBAL_VOCABULARY_TERMS = (
    "헤이 자비스",
    "헤이자비스",
    "이 자비스",
    "예 자비스",
    "왜 자비스",
    "Hey Jarvis",
    "Jarvis",
    "자비스",
    "자비스야",
)


def build_vocabulary_hint(knowledge_base_path: Path | None) -> str:
    """Extract a compact STT vocabulary hint from local indexed source files."""
    terms: list[str] = []
    seen: set[str] = set()

    for term in _GLOBAL_VOCABULARY_TERMS:
        _add_term(term, terms, seen)

    if knowledge_base_path is None:
        return _build_prompt(terms)

    resolved_kb_path = knowledge_base_path.expanduser().resolve()
    if not resolved_kb_path.exists():
        return _build_prompt(terms)

    for entry in build_identifier_lexicon(resolved_kb_path):
        _add_term(entry.canonical, terms, seen)
        for token in entry.tokens:
            _add_term(token, terms, seen)
        if len(terms) >= _MAX_TERMS:
            break

    for term in load_indexed_vocabulary_terms(_resolve_workspace_root(resolved_kb_path)):
        _add_term(term, terms, seen)
        if len(terms) >= _MAX_TERMS:
            break

    return _build_prompt(terms)


def _build_prompt(terms: list[str]) -> str:
    if not terms:
        return ""
    prompt = "Local vocabulary: " + ", ".join(terms[:_MAX_TERMS])
    return prompt[:_MAX_PROMPT_CHARS]


def _add_term(term: str, terms: list[str], seen: set[str]) -> None:
    cleaned = unicodedata.normalize("NFC", term).strip()
    lowered = cleaned.lower()
    if not cleaned or lowered in seen:
        return
    if len(cleaned) < 3:
        return
    if not any(ch.isalpha() for ch in cleaned):
        return
    seen.add(lowered)
    terms.append(cleaned)


def _resolve_workspace_root(knowledge_base_path: Path) -> Path:
    if knowledge_base_path.is_dir() and knowledge_base_path.name == "knowledge_base":
        return knowledge_base_path.parent
    if knowledge_base_path.is_file():
        return knowledge_base_path.parent
    return knowledge_base_path


def load_indexed_vocabulary_terms(workspace_root: Path | None = None) -> list[str]:
    db_path = resolve_menubar_data_dir(workspace_root) / "jarvis.db"
    if not db_path.exists():
        return []

    terms: list[str] = []
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    except sqlite3.Error:
        return []

    try:
        path_rows = conn.execute(
            "SELECT path FROM documents ORDER BY document_id LIMIT 80"
        ).fetchall()
    except sqlite3.Error:
        path_rows = []

    try:
        rows = conn.execute(
            "SELECT text FROM chunks ORDER BY chunk_id LIMIT ?",
            (_MAX_CHUNK_ROWS,),
        ).fetchall()
    except sqlite3.Error:
        rows = []

    try:
        for (path_text,) in path_rows:
            if not isinstance(path_text, str):
                continue
            for token in _extract_terms_from_path(path_text):
                terms.append(token)
                if len(terms) >= _MAX_TERMS:
                    return terms
        for (text,) in rows:
            if not isinstance(text, str):
                continue
            for token in _extract_terms_from_chunk(text):
                terms.append(token)
                if len(terms) >= _MAX_TERMS:
                    return terms
    finally:
        conn.close()

    return terms


def _extract_terms_from_chunk(text: str) -> list[str]:
    text = unicodedata.normalize("NFC", text)
    extracted: list[str] = []
    for token in _TOKEN_RE.findall(text):
        cleaned = token.strip(".,:;|[](){}\"'")
        if len(cleaned) < 2:
            continue
        if not any(ch.isalpha() or _KOREAN_RE.match(ch) for ch in cleaned):
            continue
        extracted.append(cleaned)
        extracted.extend(_expand_korean_compound_terms(cleaned))
    return extracted


def _extract_terms_from_path(path_text: str) -> list[str]:
    path_text = unicodedata.normalize("NFC", path_text)
    extracted: list[str] = []
    stem = Path(path_text).stem
    for token in _PATH_TOKEN_RE.findall(stem):
        cleaned = token.strip()
        if len(cleaned) < 2:
            continue
        extracted.append(cleaned)
        extracted.extend(_expand_korean_compound_terms(cleaned))
    return extracted


def _expand_korean_compound_terms(token: str) -> list[str]:
    if not token or not all(_KOREAN_RE.match(ch) for ch in token):
        return []
    if len(token) < 4:
        return []
    expanded: list[str] = []
    max_size = min(4, len(token))
    for size in range(2, max_size + 1):
        for index in range(0, len(token) - size + 1):
            piece = token[index:index + size]
            if piece not in expanded:
                expanded.append(piece)
    return expanded
