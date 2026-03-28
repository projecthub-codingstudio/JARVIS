"""Speech transcript repair helpers.

This module owns the stage between raw STT output and semantic query
normalization:

    raw transcript -> STT repair -> display correction -> final handoff

It intentionally does not perform retrieval-oriented identifier expansion.
"""

from __future__ import annotations

from dataclasses import dataclass
import re

_CLAUSE_SPLIT_RE = re.compile(r"[.!?\n]+")
_TOKEN_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]{1,}|[가-힣]{2,}")
_REQUEST_HINT_RE = re.compile(
    r"(알려|설명|요약|정리|찾아|검색|보여|메뉴|구조|차이|무엇|어디|어떻게|왜|가능|확인|추천)",
    re.IGNORECASE,
)
_GREETING_HINT_RE = re.compile(r"(안녕|반갑|고마워|감사|수고)", re.IGNORECASE)
_TRAILING_NOISE_HINT_RE = re.compile(r"(뭐지|뭔가|왜.*?가|어쩌.*?가|웬.*?가)$")
_LEADING_GREETING_RE = re.compile(
    r"^\s*(?:안녕하세요|안녕(?:하세요)?|반갑습니다|반가워요|반가워|저기요|자비스야)\s*[,.! ]*",
    re.IGNORECASE,
)
_DIET_QUERY_HINT_RE = re.compile(
    r"(다이어트|식단표|식단|메뉴\s*표|메뉴표|아침|점심|저녁|조식|중식|석식)",
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
_DIET_DAY_NUMBER_WORD_RE = re.compile(
    r"(?<!\d)(?P<number>열한|열두|열세|열세|열네|열다섯|열여섯|열일곱|열여덟|열아홉|스물|스무|"
    r"하나|한|둘|두|셋|세|넷|네|다섯|여섯|일곱|여덟|아홉|열|"
    r"십구|십팔|십칠|십육|십오|십사|십삼|십이|십일|십|"
    r"구|팔|칠|육|오|사|삼|이|일)\s*(?:(?:일|1)\s*)?"
    r"(?:차|회차|일자|번째|번)",
    re.IGNORECASE,
)
_DIET_DAY_NUMBER_DIGIT_RE = re.compile(
    r"(?P<number>\d{1,2})\s*(?:(?:일|1)\s*)?"
    r"(?:차|회차|일자|번째|번)",
    re.IGNORECASE,
)
_DIET_DAY_PREFIX_NOISE_RE = re.compile(
    r"(?<!\d)일\s+"
    r"(?P<number>\d{1,2}|열한|열두|열세|열세|열네|열다섯|열여섯|열일곱|열여덟|열아홉|스물|스무|"
    r"하나|한|둘|두|셋|세|넷|네|다섯|여섯|일곱|여덟|아홉|열|"
    r"십구|십팔|십칠|십육|십오|십사|십삼|십이|십일|십|"
    r"구|팔|칠|육|오|사|삼|이|일)"
    r"\s*(?:(?:일|1)\s*)?(?:차|회차|일자|번째|번)?"
    r"(?=\s*(?:아침|점심|저녁|조식|중식|석식|메뉴|식단))",
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
_DIET_TABLE_REPLACEMENTS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"다이어트\s+식단\s*메뉴\s*표?", re.IGNORECASE), "다이어트 식단표"),
    (re.compile(r"다이어트\s+메뉴\s*표", re.IGNORECASE), "다이어트 식단표"),
    (re.compile(r"식단\s*메뉴\s*표?", re.IGNORECASE), "식단표"),
    (re.compile(r"메뉴\s*표", re.IGNORECASE), "식단표"),
)
_DIET_MEAL_REPLACEMENTS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\b조식\b", re.IGNORECASE), "아침"),
    (re.compile(r"\b중식\b", re.IGNORECASE), "점심"),
    (re.compile(r"\b석식\b", re.IGNORECASE), "저녁"),
)
_NON_CODE_IDENTIFIER_TAIL_RE = re.compile(r"(?:\s+[A-Za-z_][A-Za-z0-9_]{2,}){2,}\s*$")


@dataclass(frozen=True)
class TranscriptRepairResult:
    raw_text: str
    repaired_text: str
    display_text: str
    final_query: str


def _normalize_whitespace(text: str) -> str:
    return " ".join(text.split()).strip()


def _extract_content_tokens(text: str) -> list[str]:
    seen: list[str] = []
    for token in _TOKEN_RE.findall(text):
        lowered = token.lower()
        if len(lowered) < 2:
            continue
        if lowered not in seen:
            seen.append(lowered)
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

    clauses = [
        _normalize_whitespace(part)
        for part in _CLAUSE_SPLIT_RE.split(normalized)
        if _normalize_whitespace(part)
    ]
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


def _repair_korean_day_expressions(text: str) -> str:
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


def _looks_like_diet_menu_query(text: str) -> bool:
    return bool(_DIET_QUERY_HINT_RE.search(text))


def _canonicalize_diet_query_terms(text: str) -> str:
    normalized = text
    for pattern, replacement in _DIET_TABLE_REPLACEMENTS:
        normalized = pattern.sub(replacement, normalized)
    for pattern, replacement in _DIET_MEAL_REPLACEMENTS:
        normalized = pattern.sub(replacement, normalized)
    return normalized


def _repair_diet_day_expressions(text: str) -> str:
    def replace_prefixed_noise(match: re.Match[str]) -> str:
        raw = match.group("number")
        if raw.isdigit():
            return f"{int(raw)}일차 "
        value = _DAY_NUMBER_WORDS.get(raw.lower())
        if value is None:
            return match.group(0)
        return f"{value}일차 "

    normalized = _DIET_DAY_PREFIX_NOISE_RE.sub(replace_prefixed_noise, text)

    def replace_word(match: re.Match[str]) -> str:
        raw = match.group("number")
        value = _DAY_NUMBER_WORDS.get(raw.lower())
        if value is None:
            return match.group(0)
        return f"{value}일차"

    normalized = _DIET_DAY_NUMBER_WORD_RE.sub(replace_word, normalized)

    def replace_digit(match: re.Match[str]) -> str:
        return f"{int(match.group('number'))}일차"

    return _DIET_DAY_NUMBER_DIGIT_RE.sub(replace_digit, normalized)


def _repair_domain_slots(text: str) -> str:
    normalized = text
    if _looks_like_diet_menu_query(normalized):
        normalized = _canonicalize_diet_query_terms(normalized)
        normalized = _repair_diet_day_expressions(normalized)
    return normalized


def repair_stt_transcript(text: str) -> str:
    cleaned = _select_spoken_clauses(text)
    cleaned = _repair_korean_day_expressions(cleaned)
    cleaned = _repair_domain_slots(cleaned)
    return _normalize_whitespace(cleaned)


def correct_transcript_for_display(text: str) -> str:
    cleaned = _normalize_whitespace(text)
    if not cleaned:
        return ""
    cleaned = _LEADING_GREETING_RE.sub("", cleaned, count=1) or cleaned

    lowered = cleaned.lower()
    looks_like_code_query = any(
        token in lowered
        for token in ("코드", "소스", "클래스", "함수", ".py", ".ts", ".js")
    )
    if not looks_like_code_query:
        match = _NON_CODE_IDENTIFIER_TAIL_RE.search(cleaned)
        if match is not None:
            tail = cleaned[match.start():].lower()
            if "_" in tail or "min_" in tail or "failure" in tail:
                cleaned = cleaned[:match.start()].rstrip()
    return cleaned


def build_transcript_repair(text: str) -> TranscriptRepairResult:
    raw_text = _normalize_whitespace(text)
    repaired_text = repair_stt_transcript(raw_text)
    display_text = correct_transcript_for_display(repaired_text)
    return TranscriptRepairResult(
        raw_text=raw_text,
        repaired_text=repaired_text,
        display_text=display_text,
        final_query=display_text,
    )


def prepare_transcript_for_query(text: str) -> str:
    return build_transcript_repair(text).final_query
