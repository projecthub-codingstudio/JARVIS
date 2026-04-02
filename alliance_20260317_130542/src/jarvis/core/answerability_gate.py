"""Pre-generation answerability gate for unsupported or ambiguous questions."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import unicodedata

from jarvis.contracts import EvidenceItem, VerifiedEvidenceSet

_TOKEN_RE = re.compile(r"[0-9A-Za-z가-힣_./-]+")
_FILENAME_RE = re.compile(
    r"[\w.-]+\.(?:py|ts|tsx|js|jsx|sql|md|txt|json|yaml|yml|csv|docx|pptx|xlsx|pdf|hwp|hwpx)"
)
_UNDERSPECIFIED_RE = re.compile(
    r"(그거|이거|저거|그 파일|이 파일|저 파일|그 문서|이 문서|저 문서|"
    r"that file|that document|that doc|그 일정|그 모델|이 일정|이 모델)",
    re.IGNORECASE,
)
_QUESTION_PROMPT_RE = re.compile(r"(무엇|뭐|어디|어느|언제|누구|몇|얼마|알려|설명|정리|요약)")
_STOPWORDS = {
    "the", "a", "an", "is", "are", "what", "which", "who", "when", "where", "why", "how",
    "please", "document", "documents", "file", "files", "doc", "docs",
    "알려", "알려줘", "알려주세요", "설명", "설명해", "설명해줘", "설명해주세요",
    "정리", "요약", "문서", "파일", "자료", "코드", "소스", "내용", "정보", "관련",
    "그거", "이거", "저거", "그", "이", "저", "해주세요", "주세요", "좀",
}
_PARTICLE_SUFFIXES = (
    "에서", "으로", "에게", "까지", "부터", "처럼", "보다", "만", "도", "은", "는",
    "이", "가", "을", "를", "에", "의", "와", "과", "로", "랑", "하고",
)
_TABLE_FILE_SUFFIXES = {".xlsx", ".csv", ".tsv"}
_TABLE_FIELD_ALIASES = {
    "breakfast": ("breakfast", "아침", "조식"),
    "lunch": ("lunch", "점심", "중식"),
    "dinner": ("dinner", "저녁", "석식"),
    "drinks": ("drinks", "drink", "음료"),
}


@dataclass(frozen=True)
class AnswerabilityAssessment:
    decision: str
    reason_code: str
    confidence: float
    message: str = ""


class AnswerabilityGate:
    """Decide whether JARVIS should answer, clarify, or abstain."""

    def assess(
        self,
        *,
        query: str,
        evidence: VerifiedEvidenceSet,
        analysis: object | None = None,
    ) -> AnswerabilityAssessment:
        if evidence.is_empty:
            return AnswerabilityAssessment(
                decision="abstain",
                reason_code="no_evidence",
                confidence=1.0,
                message="관련 증거를 찾을 수 없어 답변을 생성할 수 없습니다.",
            )

        top_items = list(evidence.items[:3])
        top_item = top_items[0]
        top_score = max(0.0, top_item.relevance_score)
        second_score = max(0.0, top_items[1].relevance_score) if len(top_items) > 1 else 0.0
        score_margin = top_score - second_score

        query_terms = _extract_query_terms(query)
        target_file = str(getattr(analysis, "target_file", "") or "").strip()

        if target_file and not _target_file_matched(target_file, top_items):
            return AnswerabilityAssessment(
                decision="abstain",
                reason_code="target_file_mismatch",
                confidence=0.93,
                message=(
                    f"질문에서 지정한 `{target_file}` 파일과 일치하는 근거를 찾지 못했습니다. "
                    "파일명이나 대상 문서를 다시 확인해 주세요."
                ),
            )

        filename_mentions = _FILENAME_RE.findall(query)
        if filename_mentions and not any(_target_file_matched(name, top_items) for name in filename_mentions):
            return AnswerabilityAssessment(
                decision="abstain",
                reason_code="filename_mismatch",
                confidence=0.9,
                message="질문에서 언급한 파일과 일치하는 근거를 찾지 못했습니다. 파일명을 다시 확인해 주세요.",
            )

        if _supports_structured_table_lookup(list(evidence.items[:5]), analysis):
            return AnswerabilityAssessment(
                decision="answer",
                reason_code="table_lookup_supported",
                confidence=0.88,
            )

        top_overlap = _best_overlap(top_item, query_terms)
        top_overlap_ratio = _overlap_ratio(top_overlap, query_terms)
        second_overlap = _best_overlap(top_items[1], query_terms) if len(top_items) > 1 else 0
        second_overlap_ratio = _overlap_ratio(second_overlap, query_terms)

        if query_terms and top_overlap == 0 and top_score < 0.22:
            return AnswerabilityAssessment(
                decision="abstain",
                reason_code="query_evidence_mismatch",
                confidence=0.9,
                message=(
                    "현재 검색된 근거가 질문의 핵심 표현과 맞지 않아 바로 답하면 잘못된 안내가 될 수 있습니다. "
                    "대상 문서나 정확한 항목명을 더 구체적으로 알려주시면 다시 확인하겠습니다."
                ),
            )

        if top_score < 0.08 and top_overlap_ratio < 0.34:
            return AnswerabilityAssessment(
                decision="abstain",
                reason_code="weak_evidence",
                confidence=0.86,
                message=(
                    "현재 검색된 근거만으로는 질문의 전제를 확인할 수 없습니다. "
                    "질문의 대상 문서나 정확한 키워드를 조금 더 구체적으로 알려주세요."
                ),
            )

        if _is_underspecified(query):
            if len(top_items) > 1 and _looks_ambiguous(top_items, top_overlap, second_overlap, score_margin):
                return AnswerabilityAssessment(
                    decision="clarify",
                    reason_code="underspecified_query",
                    confidence=0.84,
                    message=_clarification_message(top_items),
                )
            if not query_terms and _QUESTION_PROMPT_RE.search(query):
                return AnswerabilityAssessment(
                    decision="clarify",
                    reason_code="underspecified_query",
                    confidence=0.74,
                    message="질문의 대상이 되는 문서나 항목이 불분명합니다. 어떤 문서나 파일을 말씀하시는지 알려주세요.",
                )

        if len(top_items) > 1 and _looks_ambiguous(top_items, top_overlap, second_overlap, score_margin):
            return AnswerabilityAssessment(
                decision="clarify",
                reason_code="ambiguous_sources",
                confidence=0.72,
                message=_clarification_message(top_items),
            )

        return AnswerabilityAssessment(
            decision="answer",
            reason_code="supported",
            confidence=0.8 if top_overlap_ratio >= 0.5 or top_score >= 0.16 else 0.62,
        )


def _extract_query_terms(text: str) -> list[str]:
    terms: list[str] = []
    seen: set[str] = set()
    for raw in _TOKEN_RE.findall(text.lower()):
        token = raw.strip(".,?!;:()[]{}\"'")
        if not token or token.isdigit():
            continue
        for suffix in _PARTICLE_SUFFIXES:
            if token.endswith(suffix) and len(token) > len(suffix) + 1:
                token = token[: -len(suffix)]
                break
        if len(token) < 2 or token in _STOPWORDS:
            continue
        if token in seen:
            continue
        seen.add(token)
        terms.append(token)
    return terms


def _item_text(item: EvidenceItem) -> str:
    source_name = _normalize_match_text(Path(item.source_path).name) if item.source_path else ""
    heading = _normalize_match_text(str(item.heading_path or ""))
    body = _normalize_match_text(item.text)
    return " ".join(part.lower() for part in (source_name, heading, body) if part)


def _best_overlap(item: EvidenceItem, query_terms: list[str]) -> int:
    if not query_terms:
        return 0
    haystack = _item_text(item)
    return sum(1 for term in query_terms if term in haystack)


def _overlap_ratio(overlap_count: int, query_terms: list[str]) -> float:
    if not query_terms:
        return 0.0
    return overlap_count / max(1, len(query_terms))


def _target_file_matched(target_file: str, items: list[EvidenceItem]) -> bool:
    normalized = _normalize_match_text(target_file).lower().strip()
    return any(
        normalized and normalized in _normalize_match_text(Path(item.source_path).name).lower()
        for item in items
        if item.source_path
    )


def _is_underspecified(query: str) -> bool:
    return bool(_UNDERSPECIFIED_RE.search(query))


def _looks_ambiguous(
    items: list[EvidenceItem],
    top_overlap: int,
    second_overlap: int,
    score_margin: float,
) -> bool:
    if len(items) < 2:
        return False
    first_source = items[0].source_path or items[0].document_id
    second_source = items[1].source_path or items[1].document_id
    if not first_source or not second_source or first_source == second_source:
        return False
    if abs(top_overlap - second_overlap) > 1:
        return False
    return score_margin <= 0.08


def _clarification_message(items: list[EvidenceItem]) -> str:
    candidates: list[str] = []
    for item in items[:2]:
        source = Path(item.source_path).name if item.source_path else item.document_id
        if source and source not in candidates:
            candidates.append(source)
    if len(candidates) >= 2:
        return (
            f"질문의 대상이 불분명합니다. `{candidates[0]}`와 `{candidates[1]}` 중 어느 쪽을 말씀하시는지 알려주세요."
        )
    return "질문의 대상이 불분명합니다. 어떤 문서나 파일을 말씀하시는지 조금 더 구체적으로 알려주세요."


def _supports_structured_table_lookup(items: list[EvidenceItem], analysis: object | None) -> bool:
    if str(getattr(analysis, "retrieval_task", "") or "") != "table_lookup":
        return False

    entities = getattr(analysis, "entities", {}) or {}
    if not isinstance(entities, dict):
        return False

    row_ids = tuple(
        str(value).strip()
        for value in entities.get("row_ids", ())
        if str(value).strip()
    )
    fields = tuple(
        str(value).strip()
        for value in entities.get("fields", ())
        if str(value).strip()
    )
    if not row_ids and not fields:
        return False

    candidate_items = [item for item in items if _looks_like_table_item(item)]
    if not candidate_items:
        return False

    matched_rows: set[str] = set()
    matched_fields: set[str] = set()
    for item in candidate_items:
        haystack = _item_text(item)
        for row_id in row_ids:
            if _table_row_matched(haystack, row_id):
                matched_rows.add(row_id)
        for field in fields:
            if _table_field_matched(haystack, field):
                matched_fields.add(field.lower())

    if row_ids and not set(row_ids).issubset(matched_rows):
        return False
    if fields and not {field.lower() for field in fields}.issubset(matched_fields):
        return False
    return True


def _looks_like_table_item(item: EvidenceItem) -> bool:
    suffix = Path(item.source_path).suffix.lower() if item.source_path else ""
    if suffix in _TABLE_FILE_SUFFIXES:
        return True
    heading = str(item.heading_path or "").lower()
    if heading.startswith("table-row-"):
        return True
    haystack = _item_text(item)
    return "day=" in haystack or "breakfast=" in haystack or "lunch=" in haystack or "dinner=" in haystack


def _table_row_matched(haystack: str, row_id: str) -> bool:
    escaped = re.escape(row_id)
    return bool(
        re.search(rf"(?:\bday\s*=\s*{escaped}\b|\bday\s+{escaped}\b|{escaped}\s*일차)", haystack)
    )


def _table_field_matched(haystack: str, field: str) -> bool:
    normalized = field.strip().lower()
    aliases = {normalized}
    aliases.update(_TABLE_FIELD_ALIASES.get(normalized, ()))
    aliases.add(normalized.replace("_", " "))
    aliases.add(normalized.replace("_", ""))
    return any(alias and alias in haystack for alias in aliases)


def _normalize_match_text(text: str) -> str:
    return unicodedata.normalize("NFC", text)
