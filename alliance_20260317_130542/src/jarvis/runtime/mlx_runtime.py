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
import unicodedata
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
_TABLE_KEY_VALUE_RE = re.compile(r"([A-Za-z][A-Za-z ]+)=([^|]+)")
_DAY_QUERY_RE = re.compile(r"(\d+)\s*(?:일\s*차|일차|day|번)", re.IGNORECASE)
_TABLE_REQUEST_TOKEN_RE = re.compile(
    r"(?P<day>(?P<day_number>\d+)\s*(?:일\s*차|일차|day|번))"
    r"|(?P<meal>아침|조식|breakfast|점심|중식|lunch|저녁|석식|dinner|음료|drink|drinks)",
    re.IGNORECASE,
)
_STRUCTURED_TABLE_SUFFIXES = {".xlsx", ".csv", ".tsv"}
_TABLE_VALUE_TOKEN_RE = re.compile(r"^(.+?)(\d+)(장|개|알|잔|봉|봉지|팩|캡슐|정|스푼|큰술|작은술|g|kg|ml|l)?$")
_FRACTION_RE = re.compile(r"(\d+)\s*/\s*(\d+)")
_QUERY_TERM_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]{1,}|[가-힣]{2,}")
_SEGMENT_SPLIT_RE = re.compile(r"[\n\r]+|(?<=[.!?])\s+|\s+\|\s+")
_BRACKET_PREFIX_RE = re.compile(r"^\[[^\]]+\]\s*")
_NOISE_TOKEN_RE = re.compile(r"^(?:오프셋|자료형|의미|설명|길이|바이트|입력시|table|columns?)$", re.IGNORECASE)
_EXPLANATORY_PHRASE_RE = re.compile(r"(?:이다|있다|된다|한다|의미|설명|구조로 저장|때문에|가능하다|존재한다)")
_SENTENCE_END_RE = re.compile(r"(?<=[.!?])\s+")
_PATH_LIKE_SEGMENT_RE = re.compile(r"(?:/[^/\s]+){2,}|\\[^\\\s]+(?:\\[^\\\s]+){1,}|]\(|workspace/|#L\d+", re.IGNORECASE)

_KOREAN_NUMBER_WORDS = {
    0: "영",
    1: "한",
    2: "두",
    3: "세",
    4: "네",
    5: "다섯",
    6: "여섯",
    7: "일곱",
    8: "여덟",
    9: "아홉",
    10: "열",
}
_SINO_KOREAN_NUMBER_WORDS = {
    0: "영",
    1: "일",
    2: "이",
    3: "삼",
    4: "사",
    5: "오",
    6: "육",
    7: "칠",
    8: "팔",
    9: "구",
    10: "십",
}
_KOREAN_UNIT_LABELS = {
    "g": "그램",
    "kg": "킬로그램",
    "ml": "밀리리터",
    "l": "리터",
}
_QUERY_STOPWORDS = {
    "알려줘", "알려주세요", "설명", "설명해", "설명해줘", "설명해주세요", "대해", "대해서",
    "그리고", "에서", "중에", "해주세요",
    "요약", "정리", "좀", "관련", "반갑습니다", "안녕하세요", "만나서",
}
_KOREAN_POSTPOSITION_SUFFIXES = (
    "에서", "으로", "에게", "까지", "부터", "처럼", "보다", "만", "도", "은", "는", "이", "가",
    "을", "를", "에", "의", "와", "과", "로", "랑", "하고",
)


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


def build_stub_spoken_response(prompt: str, evidence: VerifiedEvidenceSet) -> str:
    if table_response := _build_table_stub_response(prompt, evidence, spoken=True):
        return table_response
    return ""


def _build_stub_grounded_response(prompt: str, evidence: VerifiedEvidenceSet) -> str:
    if table_response := _build_table_stub_response(prompt, evidence, spoken=False):
        return _append_primary_citation_if_missing(table_response, evidence)
    head = _extract_best_stub_snippet(prompt, evidence)
    identifier = _extract_requested_identifier(prompt, evidence)

    if re.search(r"(?:\bclass\b|클래스)", prompt, re.IGNORECASE):
        if identifier:
            intro = f"`{identifier}` 클래스는 다음과 같이 정의되어 있습니다."
        else:
            intro = "요청하신 클래스의 핵심 정의는 다음과 같습니다."
        return _append_primary_citation_if_missing(f"{intro} {head}".strip(), evidence)

    return _append_primary_citation_if_missing(head, evidence)


def _append_primary_citation_if_missing(text: str, evidence: VerifiedEvidenceSet) -> str:
    rendered = text.strip()
    if not rendered:
        return text
    if re.search(r"\[\d+\]", rendered):
        return rendered
    if evidence.is_empty:
        return rendered

    primary_label = evidence.items[0].citation.label.strip()
    if not primary_label:
        return rendered
    return f"{rendered} {primary_label}"


def _build_table_stub_response(
    prompt: str,
    evidence: VerifiedEvidenceSet,
    *,
    spoken: bool = False,
) -> str:
    table_items = [
        item for item in evidence.items
        if item.heading_path and "table-row" in item.heading_path and _is_structured_table_item(item)
    ]
    if not table_items:
        return ""

    requested_days = [int(day) for day in _DAY_QUERY_RE.findall(prompt)]
    requested_fields = _requested_table_fields(prompt)
    requested_pairs = _requested_table_field_pairs(prompt)
    rendered_rows: list[str] = []

    for item in table_items:
        parsed = _parse_table_row(item.text)
        if not parsed:
            continue
        day = parsed.get("Day", "").strip()
        if requested_days and day.isdigit() and int(day) not in requested_days:
            continue
        pair_fields: list[str] | None = None
        if requested_pairs and day.isdigit():
            pair_fields = requested_pairs.get(int(day))
            if pair_fields is None:
                continue
        rendered = _render_table_row(
            parsed,
            requested_fields=pair_fields if pair_fields is not None else requested_fields,
            spoken=spoken,
        )
        if rendered and rendered not in rendered_rows:
            rendered_rows.append(rendered)

    if not rendered_rows:
        return ""

    if requested_fields:
        return " / ".join(rendered_rows[:3])
    return " ".join(rendered_rows[:3])


def _requested_table_fields(prompt: str) -> list[str] | None:
    lowered = prompt.lower()
    field_aliases = {
        "Breakfast": ("아침", "조식", "breakfast"),
        "Lunch": ("점심", "중식", "lunch"),
        "Dinner": ("저녁", "석식", "dinner"),
        "Drinks": ("음료", "drink", "drinks"),
    }
    matched_fields: list[str] = []
    for field, aliases in field_aliases.items():
        if any(alias in lowered for alias in aliases):
            matched_fields.append(field)
    if matched_fields:
        return matched_fields
    if "메뉴" in prompt:
        return ["Breakfast", "Lunch", "Dinner"]
    return None


def _requested_table_field_pairs(prompt: str) -> dict[int, list[str]] | None:
    pending_days: list[int] = []
    pairs: dict[int, list[str]] = {}
    last_kind = ""

    for match in _TABLE_REQUEST_TOKEN_RE.finditer(prompt):
        day_number = match.group("day_number")
        if day_number is not None:
            day_value = int(day_number)
            if last_kind == "field":
                pending_days = [day_value]
            elif day_value not in pending_days:
                pending_days.append(day_value)
            last_kind = "day"
            continue

        meal_alias = match.group("meal")
        field = _table_field_for_alias(meal_alias or "")
        if field is None or not pending_days:
            continue
        for day_value in pending_days:
            day_fields = pairs.setdefault(day_value, [])
            if field not in day_fields:
                day_fields.append(field)
        last_kind = "field"

    return pairs or None


def _table_field_for_alias(alias: str) -> str | None:
    lowered = alias.lower()
    field_aliases = {
        "Breakfast": ("아침", "조식", "breakfast"),
        "Lunch": ("점심", "중식", "lunch"),
        "Dinner": ("저녁", "석식", "dinner"),
        "Drinks": ("음료", "drink", "drinks"),
    }
    for field, aliases in field_aliases.items():
        if lowered in aliases:
            return field
    return None


def _is_structured_table_item(item) -> bool:
    if not item.source_path:
        return True
    return Path(item.source_path).suffix.lower() in _STRUCTURED_TABLE_SUFFIXES


def _parse_table_row(text: str) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for key, value in _TABLE_KEY_VALUE_RE.findall(text):
        parsed[key.strip()] = value.strip()
    return parsed


def _render_table_row(
    parsed: dict[str, str],
    *,
    requested_fields: list[str] | None,
    spoken: bool = False,
) -> str:
    day = parsed.get("Day", "").strip()
    field_labels = {
        "Breakfast": "아침",
        "Lunch": "점심",
        "Dinner": "저녁",
        "Drinks": "음료",
    }

    if requested_fields:
        parts = []
        for field in requested_fields:
            value = parsed.get(field, "").strip()
            if value:
                rendered_value = _render_table_value(value, spoken=spoken)
                parts.append(f"{field_labels.get(field, field)}은 {rendered_value}")
        if day and parts:
            if len(parts) == 1:
                return f"{day}일차 {parts[0]}입니다."
            return f"{day}일차 메뉴는 " + ", ".join(parts) + "입니다."
        return ""

    value_parts = []
    for key in ("Breakfast", "Lunch", "Dinner"):
        value = parsed.get(key, "").strip()
        if value:
            value_parts.append(_render_table_value(value, spoken=spoken))
    if day and value_parts:
        return f"{day}일차 식단은 " + ", ".join(value_parts) + "입니다."
    return ""


def _render_table_value(value: str, *, spoken: bool) -> str:
    normalized = " ".join(value.split())
    if not spoken:
        return normalized
    return _naturalize_table_value(normalized)


def _naturalize_table_value(value: str) -> str:
    parts = [part.strip() for part in re.split(r"\s*\+\s*", value) if part.strip()]
    if len(parts) > 1:
        rendered_parts = [_naturalize_table_atom(part) for part in parts]
        return _join_with_korean_and(rendered_parts)
    return _naturalize_table_atom(value)


def _naturalize_table_atom(atom: str) -> str:
    atom = atom.strip()
    if not atom:
        return atom

    atom = _FRACTION_RE.sub(lambda match: _render_fraction(match.group(1), match.group(2)), atom)
    atom = re.sub(
        r"(?<=[가-힣A-Za-z])(?=(?:영|일|이|삼|사|오|육|칠|팔|구|십) 분의)",
        " ",
        atom,
    )

    match = _TABLE_VALUE_TOKEN_RE.match(atom)
    if match:
        name, number, unit = match.groups()
        spoken_number = _render_counter_number(number, unit)
        spoken_unit = _KOREAN_UNIT_LABELS.get((unit or "").lower(), unit or "개")
        name = name.strip()
        if spoken_unit:
            return f"{name} {spoken_number} {spoken_unit}".strip()
        return f"{name} {spoken_number}".strip()

    atom = atom.replace("~", "에서 ")
    atom = atom.replace(",", ", ")
    atom = re.sub(r"\s+", " ", atom)
    return atom.strip()


def _render_fraction(numerator: str, denominator: str) -> str:
    return f"{_sino_korean_number(int(denominator))} 분의 {_sino_korean_number(int(numerator))}"


def _join_with_korean_and(parts: list[str]) -> str:
    if not parts:
        return ""
    if len(parts) == 1:
        return parts[0]
    result = parts[0]
    for part in parts[1:]:
        particle = _korean_and_particle(result)
        result = f"{result}{particle} {part}"
    return result


def _korean_and_particle(text: str) -> str:
    stripped = text.strip()
    if not stripped:
        return "와"
    last = stripped[-1]
    if not ("\uac00" <= last <= "\ud7a3"):
        return "와"
    return "과" if (ord(last) - 0xAC00) % 28 else "와"


def _render_counter_number(number: str, unit: str | None) -> str:
    value = int(number)
    if unit and unit.lower() in {"g", "kg", "ml", "l"}:
        return _sino_korean_number(value)
    return _korean_counter_number(value)


def _korean_counter_number(value: int) -> str:
    return _KOREAN_NUMBER_WORDS.get(value, str(value))


def _sino_korean_number(value: int) -> str:
    return _SINO_KOREAN_NUMBER_WORDS.get(value, str(value))


def _extract_best_stub_snippet(prompt: str, evidence: VerifiedEvidenceSet) -> str:
    if not evidence.items:
        return ""
    primary_source = evidence.items[0].source_path or ""
    wants_class = bool(re.search(r"(?:\bclass\b|클래스)", prompt, re.IGNORECASE))
    wants_function = bool(re.search(r"(?:\bfunction\b|\bmethod\b|\bdef\b|함수|메서드|메소드)", prompt, re.IGNORECASE))
    identifier = _extract_requested_identifier(prompt, evidence)

    if primary_source and (wants_class or wants_function):
        extracted = _extract_source_snippet(
            source_path=primary_source,
            identifier=identifier,
            wants_class=wants_class,
            wants_function=wants_function,
        )
        if extracted:
            return extracted

    primary_excerpt = _extract_primary_evidence_excerpt(prompt, evidence)
    if primary_excerpt:
        return primary_excerpt

    document_excerpt = _extract_relevant_document_excerpt(prompt, evidence)
    if document_excerpt:
        return document_excerpt

    head = evidence.items[0].text.strip()
    head = re.sub(r"\s+", " ", head)
    return head[:220].rstrip()


def _extract_relevant_document_excerpt(prompt: str, evidence: VerifiedEvidenceSet) -> str:
    query_terms = _extract_stub_query_terms(prompt, evidence)
    if not query_terms:
        return ""

    best_segment = ""
    best_score = -1.0
    best_segments: list[str] = []
    best_segment_index = -1
    for item_index, item in enumerate(evidence.items[:5]):
        item_segments = _split_document_segments(item.text)
        for segment_index, segment in enumerate(item_segments):
            score = _score_document_segment(segment, query_terms)
            if score <= 0:
                continue
            score += _score_heading_match(item.heading_path, query_terms, segment)
            score += _score_source_path_match(item.source_path, query_terms)
            # Favor earlier high-ranking evidence items but still let content relevance dominate.
            score += max(0.0, 1.0 - (item_index * 0.1) - (segment_index * 0.02))
            if score > best_score:
                best_score = score
                best_segment = segment
                best_segments = item_segments
                best_segment_index = segment_index

    if not best_segment:
        return ""
    return _expand_stub_excerpt(best_segment, best_segments, best_segment_index)


def _extract_primary_evidence_excerpt(prompt: str, evidence: VerifiedEvidenceSet) -> str:
    if not evidence.items:
        return ""
    query_terms = _extract_stub_query_terms(prompt, evidence)
    if not query_terms:
        return ""

    primary_item = evidence.items[0]
    if (
        _score_source_path_match(primary_item.source_path, query_terms) <= 0
        and _score_heading_match(primary_item.heading_path, query_terms) <= 0
    ):
        return ""

    segments = _split_document_segments(primary_item.text)
    if not segments:
        return re.sub(r"\s+", " ", primary_item.text.strip())[:220].rstrip()

    best_segment = ""
    best_score = -1.0
    best_index = -1
    for index, segment in enumerate(segments):
        score = _score_document_segment(segment, query_terms)
        if score <= 0:
            continue
        score += _score_heading_match(primary_item.heading_path, query_terms, segment)
        score += _score_source_path_match(primary_item.source_path, query_terms)
        if score > best_score:
            best_score = score
            best_segment = segment
            best_index = index

    if not best_segment:
        return re.sub(r"\s+", " ", primary_item.text.strip())[:220].rstrip()
    return _expand_stub_excerpt(best_segment, segments, best_index)


def _extract_stub_query_terms(prompt: str, evidence: VerifiedEvidenceSet) -> list[str]:
    query_terms = _extract_query_terms(prompt)
    for fragment in evidence.query_fragments:
        for term in _extract_query_terms(fragment.text):
            if term not in query_terms:
                query_terms.append(term)
    return query_terms


def _extract_query_terms(prompt: str) -> list[str]:
    terms: list[str] = []
    for token in _QUERY_TERM_RE.findall(prompt):
        normalized = _normalize_query_token(token)
        if len(normalized) < 2:
            continue
        if normalized in _QUERY_STOPWORDS:
            continue
        if _NOISE_TOKEN_RE.match(normalized):
            continue
        if normalized not in terms:
            terms.append(normalized)
    return terms


def _normalize_query_token(token: str) -> str:
    normalized = token.strip().lower()
    for suffix in _KOREAN_POSTPOSITION_SUFFIXES:
        if normalized.endswith(suffix) and len(normalized) > len(suffix) + 1:
            normalized = normalized[: -len(suffix)]
            break
    return normalized


def _split_document_segments(text: str) -> list[str]:
    normalized = _BRACKET_PREFIX_RE.sub("", text.strip())
    raw_segments = [segment.strip() for segment in _SEGMENT_SPLIT_RE.split(normalized) if segment.strip()]
    cleaned_segments: list[str] = []
    for segment in raw_segments:
        collapsed = re.sub(r"\s+", " ", segment).strip(" -:")
        if len(collapsed) < 12:
            if len(collapsed) < 8:
                continue
            if not (_EXPLANATORY_PHRASE_RE.search(collapsed) or collapsed.endswith((".", "!", "?"))):
                continue
        cleaned_segments.append(_truncate_stub_segment(collapsed))
    return cleaned_segments[:20]


def _truncate_stub_segment(segment: str, *, max_chars: int = 320) -> str:
    normalized = re.sub(r"\s+", " ", segment).strip()
    if len(normalized) <= max_chars:
        return normalized

    candidate = normalized[:max_chars].rstrip()
    sentence_parts = [part.strip() for part in _SENTENCE_END_RE.split(candidate) if part.strip()]
    if len(sentence_parts) >= 2:
        rebuilt = " ".join(sentence_parts[:-1]).strip()
        if len(rebuilt) >= 40:
            return rebuilt

    last_punct = max(candidate.rfind("."), candidate.rfind("!"), candidate.rfind("?"))
    if last_punct >= 40:
        return candidate[: last_punct + 1].strip()

    last_space = candidate.rfind(" ")
    if last_space >= 40:
        return candidate[:last_space].strip()
    return candidate


def _expand_stub_excerpt(segment: str, segments: list[str], segment_index: int) -> str:
    if not segment or not segments or segment_index < 0:
        return segment
    combined = segment
    if segment_index + 1 < len(segments):
        next_segment = segments[segment_index + 1]
        if _is_useful_followup_segment(next_segment):
            candidate = f"{combined} {next_segment}".strip()
            if len(candidate) <= 320:
                combined = candidate
    return combined


def _is_useful_followup_segment(segment: str) -> bool:
    compact = segment.strip()
    if len(compact) < 12:
        if len(compact) < 8:
            return False
        if not (_EXPLANATORY_PHRASE_RE.search(compact) or compact.endswith((".", "!", "?"))):
            return False
    if _is_heading_like_segment(compact) and not (
        _EXPLANATORY_PHRASE_RE.search(compact) or compact.endswith((".", "!", "?"))
    ):
        return False
    if _NOISE_TOKEN_RE.match(compact.lower()):
        return False
    return bool(_EXPLANATORY_PHRASE_RE.search(compact)) or compact.endswith(".")


def _is_heading_like_segment(segment: str) -> bool:
    compact = segment.strip()
    if len(compact) <= 18:
        return True
    if len(compact) <= 32 and not _EXPLANATORY_PHRASE_RE.search(compact):
        return True
    return False


def _score_document_segment(segment: str, query_terms: list[str]) -> float:
    if _is_heading_like_segment(segment):
        return 0.0

    lowered = segment.lower()
    overlap_terms = [term for term in query_terms if term in lowered]
    if not overlap_terms:
        return 0.0
    if _is_path_like_segment(segment) and len(overlap_terms) <= 1:
        return 0.0

    score = float(len(overlap_terms) * 12)
    if len(segment) <= 180:
        score += 3.0

    alnum_or_korean = sum(char.isalnum() or ("\uac00" <= char <= "\ud7a3") for char in segment)
    punctuation_ratio = 1.0 - (alnum_or_korean / max(1, len(segment)))
    score -= punctuation_ratio * 8.0

    noise_hits = sum(1 for token in re.findall(r"[A-Za-z가-힣]+", lowered) if _NOISE_TOKEN_RE.match(token))
    score -= noise_hits * 1.5

    if _EXPLANATORY_PHRASE_RE.search(segment):
        score += 4.0

    return score


def _is_path_like_segment(segment: str) -> bool:
    return bool(_PATH_LIKE_SEGMENT_RE.search(segment))


def _score_heading_match(heading_path: str, query_terms: list[str], segment: str = "") -> float:
    if not heading_path:
        return 0.0
    lowered = heading_path.lower()
    segment_lowered = segment.lower()
    overlap_terms = [term for term in query_terms if term in lowered]
    if not overlap_terms:
        return 0.0
    heading_only_terms = [term for term in overlap_terms if term not in segment_lowered]
    return float(len(overlap_terms) * 6 + len(heading_only_terms) * 8)


def _score_source_path_match(source_path: str, query_terms: list[str]) -> float:
    if not source_path:
        return 0.0
    lowered = unicodedata.normalize("NFC", Path(source_path).name).lower()
    overlap_terms = [
        term for term in query_terms
        if unicodedata.normalize("NFC", term).lower() in lowered
    ]
    if not overlap_terms:
        return 0.0
    return float(len(overlap_terms) * 10)


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
