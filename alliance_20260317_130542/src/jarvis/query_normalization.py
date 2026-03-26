"""Shared query normalization helpers."""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

from jarvis.identifier_restoration import (
    _forms_for_text,
    _similarity,
    _strip_korean_suffixes,
    rewrite_query_with_identifiers,
)
from jarvis.runtime.stt_biasing import load_indexed_vocabulary_terms

_CLAUSE_SPLIT_RE = re.compile(r"[.!?\n]+")
_TOKEN_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]{1,}|[가-힣]{2,}")
_REQUEST_HINT_RE = re.compile(
    r"(알려|설명|요약|정리|찾아|검색|보여|메뉴|구조|차이|무엇|어디|어떻게|왜|가능|확인|추천)",
    re.IGNORECASE,
)
_GREETING_HINT_RE = re.compile(r"(안녕|반갑|고마워|감사|수고)", re.IGNORECASE)
_TRAILING_NOISE_HINT_RE = re.compile(r"(뭐지|뭔가|왜.*?가|어쩌.*?가|웬.*?가)$")
_KOREAN_TOKEN_RE = re.compile(r"[가-힣]{2,}")
_KOREAN_STOPWORDS = {"안녕하세요", "반갑습니다", "설명", "알려", "주세요", "문서", "구조", "기본"}
_MIN_FUZZY_SCORE = 0.88


def _normalize_whitespace(text: str) -> str:
    return " ".join(text.split()).strip()


def _extract_content_tokens(text: str) -> list[str]:
    seen: list[str] = []
    for token in _TOKEN_RE.findall(text):
        normalized = token.lower()
        if len(normalized) < 2:
            continue
        if normalized not in seen:
            seen.append(normalized)
    return seen


def _score_clause(clause: str) -> float:
    normalized = _normalize_whitespace(clause)
    if not normalized:
        return 0.0

    tokens = _extract_content_tokens(normalized)
    score = float(len(tokens))
    if _REQUEST_HINT_RE.search(normalized):
        score += 6.0
    if _GREETING_HINT_RE.search(normalized):
        score -= 4.0
    if _TRAILING_NOISE_HINT_RE.search(normalized):
        score -= 4.0
    if len(normalized) < 10:
        score -= 2.0
    return score


def _select_spoken_clauses(text: str) -> str:
    normalized = _normalize_whitespace(text)
    if not normalized:
        return ""

    clauses = [_normalize_whitespace(part) for part in _CLAUSE_SPLIT_RE.split(normalized) if _normalize_whitespace(part)]
    if len(clauses) <= 1:
        return normalized

    scored = [(clause, _score_clause(clause)) for clause in clauses]
    best_score = max(score for _, score in scored)
    if best_score <= 0:
        return normalized

    kept: list[str] = []
    for clause, score in scored:
        if score < best_score - 2.5:
            continue
        if _GREETING_HINT_RE.search(clause) and score < best_score:
            continue
        kept.append(clause)

    if not kept:
        return normalized
    return ". ".join(kept)


def _restore_korean_vocabulary_terms(text: str) -> str:
    vocabulary = _indexed_korean_vocabulary()
    if not vocabulary:
        return text

    def replace(match: re.Match[str]) -> str:
        token = match.group(0)
        stripped = _strip_korean_suffixes(token)
        suffix = token[len(stripped):] if len(stripped) < len(token) else ""
        if stripped in _KOREAN_STOPWORDS:
            return token
        best_term = token
        best_score = 0.0
        token_forms = _forms_for_text(stripped)
        for candidate in vocabulary:
            if candidate == stripped:
                return token
            score = 0.0
            for left in token_forms:
                for right in _forms_for_text(candidate):
                    score = max(score, _similarity(left, right))
            if not set(stripped) & set(candidate):
                continue
            if score > best_score:
                best_score = score
                best_term = candidate
        if best_score >= _MIN_FUZZY_SCORE:
            return best_term + suffix
        return token

    return _KOREAN_TOKEN_RE.sub(replace, text)


@lru_cache(maxsize=1)
def _indexed_korean_vocabulary() -> tuple[str, ...]:
    terms: list[str] = []
    seen: set[str] = set()
    for term in load_indexed_vocabulary_terms():
        cleaned = term.strip()
        if len(cleaned) < 2:
            continue
        if not _KOREAN_TOKEN_RE.fullmatch(cleaned):
            continue
        if cleaned in seen:
            continue
        seen.add(cleaned)
        terms.append(cleaned)
        if len(terms) >= 400:
            break
    return tuple(terms)


def normalize_spoken_code_query(text: str, *, knowledge_base_path: Path | None = None) -> str:
    """Preserve the original query and append high-confidence identifier anchors."""
    cleaned = _select_spoken_clauses(text)
    cleaned = _restore_korean_vocabulary_terms(cleaned)
    return rewrite_query_with_identifiers(
        cleaned,
        knowledge_base_path=knowledge_base_path,
    ).rewritten_query
