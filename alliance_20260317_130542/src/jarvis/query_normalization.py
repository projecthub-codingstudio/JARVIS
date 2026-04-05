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
from jarvis.transcript_repair import prepare_transcript_for_query

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
_LEADING_GREETING_RE = re.compile(
    r"^\s*(?:안녕하세요|안녕(?:하세요)?|반갑습니다|반가워요|반가워|저기요|자비스야)\s*[,.! ]*",
    re.IGNORECASE,
)
_DAY_NUMBER_WORD_RE = re.compile(
    r"(?P<number>열한|열두|열세|열세|열네|열다섯|열여섯|열일곱|열여덟|열아홉|스물|스무|"
    r"하나|한|둘|두|셋|세|넷|네|다섯|여섯|일곱|여덟|아홉|열|"
    r"십구|십팔|십칠|십육|십오|십사|십삼|십이|십일|십|"
    r"구|팔|칠|육|오|사|삼|이|일)\s*(?:일|1)\s*차",
    re.IGNORECASE,
)
_DAY_NUMBER_DIGIT_RE = re.compile(
    r"(?P<number>\d{1,2})\s*(?:일|1)\s*차",
    re.IGNORECASE,
)
_DAY_NUMBER_WORDS = {
    "한": 1,
    "하나": 1,
    "일": 1,
    "두": 2,
    "둘": 2,
    "이": 2,
    "세": 3,
    "셋": 3,
    "삼": 3,
    "네": 4,
    "넷": 4,
    "사": 4,
    "다섯": 5,
    "오": 5,
    "여섯": 6,
    "육": 6,
    "일곱": 7,
    "칠": 7,
    "여덟": 8,
    "팔": 8,
    "아홉": 9,
    "구": 9,
    "열": 10,
    "십": 10,
    "열한": 11,
    "십일": 11,
    "열두": 12,
    "십이": 12,
    "열세": 13,
    "십삼": 13,
    "열네": 14,
    "십사": 14,
    "열다섯": 15,
    "십오": 15,
    "열여섯": 16,
    "십육": 16,
    "열일곱": 17,
    "십칠": 17,
    "열여덟": 18,
    "십팔": 18,
    "열아홉": 19,
    "십구": 19,
    "스무": 20,
    "스물": 20,
}


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


def _strip_leading_conversational_prefix(text: str) -> str:
    normalized = _normalize_whitespace(text)
    if not normalized or not _REQUEST_HINT_RE.search(normalized):
        return normalized
    stripped = _LEADING_GREETING_RE.sub("", normalized, count=1)
    return stripped or normalized


def _normalize_korean_day_expressions(text: str) -> str:
    def replace_word(match: re.Match[str]) -> str:
        raw = match.group("number")
        value = _DAY_NUMBER_WORDS.get(raw.lower())
        if value is None:
            return match.group(0)
        return f"{value}일차"

    normalized = _DAY_NUMBER_WORD_RE.sub(replace_word, text)

    def replace_digit(match: re.Match[str]) -> str:
        return f"{int(match.group('number'))}일차"

    return _DAY_NUMBER_DIGIT_RE.sub(replace_digit, normalized)


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
    cleaned = prepare_transcript_for_query(text)
    cleaned = _restore_korean_vocabulary_terms(cleaned)
    return rewrite_query_with_identifiers(
        cleaned,
        knowledge_base_path=knowledge_base_path,
    ).rewritten_query
