"""Planner — heuristic-first query planning with optional lightweight enrichment.

Per Spec Section 2.1/2.2:
  - classify(query) -> intent type
  - build_retrieval_plan(query, intent) -> normalized search keywords
  - classify_complexity(query) -> "simple" | "moderate" | "complex"

Uses a fast heuristic baseline for all queries and optionally runs a
lightweight second pass to enrich bilingual/code search terms when the
baseline is ambiguous. The planner must remain usable even when the
lightweight stage is unavailable.
"""

from __future__ import annotations

import logging
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Protocol

from jarvis.identifier_restoration import rewrite_query_with_identifiers
from jarvis.query_normalization import normalize_spoken_code_query

logger = logging.getLogger(__name__)

QueryComplexity = Literal["simple", "moderate", "complex"]
_DEFAULT_LIGHTWEIGHT = object()

_FILENAME_RE = re.compile(
    r"([\w.-]+\.(?:py|ts|tsx|js|jsx|sql|md|txt|json|yaml|yml|csv|docx|pptx|xlsx|pdf|hwp|hwpx))"
)
_KOREAN_RE = re.compile(r"[\uac00-\ud7af\u1100-\u11ff\u3130-\u318f]+")
_ASCII_RE = re.compile(r"[A-Za-z]+")
_TOKEN_RE = re.compile(r"[0-9A-Za-z가-힣_./-]+")
_NEGATION_SUFFIX_RE = re.compile(r"(말고|제외하고|제외|아니라)")
_ACTION_VERB_RE = re.compile(
    r"(열어줘|열어|실행해줘|실행해|켜줘|켜(?:[^가-힣]|$)|틀어줘|틀어|재생해줘|재생해|시작해줘|시작해)"
    r"|\b(open|launch|start|run|play)\b",
    re.IGNORECASE,
)
_STOPWORDS = {
    "the", "a", "an", "is", "are", "to", "for", "of", "and", "or", "what", "how",
    "알려줘", "알려주세요", "보여줘", "보여주세요", "찾아줘", "찾아주세요",
    "설명해줘", "설명해주세요", "무엇", "뭐", "어디", "누구", "언제", "몇", "얼마",
}
_DOCUMENT_TOPIC_STOPWORDS = _STOPWORDS | {
    "문서", "파일", "파일형식", "파일형식에서", "형식에서", "중", "중에", "대해", "대한",
    "설명", "설명해", "설명해주세요", "설명해요", "알려", "알려줘", "알려주세요",
    "해주세요", "주세요", "에서", "그", "이", "저", "것", "정보가", "말고", "아니라",
}
_TOPIC_SUFFIXES = ("에서", "으로", "를", "을", "은", "는", "이", "가", "와", "과", "의")
_SMALLTALK_GREETING_RE = re.compile(
    r"(안녕(?:하세요|하세여|하십니까)?|하이|hello|hi|nice\s+to\s+meet\s+you|"
    r"만나서\s*반갑(?:습니다|네요|고요)?|반갑(?:습니다|네|고요)?)",
    re.IGNORECASE,
)
_SMALLTALK_POLITE_RE = re.compile(
    r"(고마워|감사(?:합니다|해요)?|좋은\s*(아침|저녁|하루)|잘\s*지냈|오랜만)",
    re.IGNORECASE,
)
_WEATHER_RE = re.compile(
    r"(오늘|지금|내일|이번\s*주)?\s*(날씨|기온|비\s*오|눈\s*오|weather|forecast|temperature)",
    re.IGNORECASE,
)
_CODE_NORMALIZATION_HINT_RE = re.compile(
    r"(소스|코드|클래스|함수|메서드|메소드|변수|필드|심볼|식별자|모듈|임포트|"
    r"파이썬|자바스크립트|타입스크립트|스위프트|러스트|고랭|경로|path|"
    r"점\s*(?:파이|티에스|티에스엑스|제이에스|제이슨|에스큐엘|엠디|시에스브이|피디에프|에이치더블유피(?:엑스)?)|"
    r"닷\s*(?:파이|티에스|티에스엑스|제이에스|제이슨|에스큐엘|엠디|시에스브이|피디에프|에이치더블유피(?:엑스)?)|"
    r"\bclass\b|\bdef\b|\bfunction\b|\bmethod\b|\bmodule\b|\bimport\b|"
    r"\.py\b|\.ts\b|\.tsx\b|\.js\b|\.jsx\b|\.sql\b|\.java\b|\.kt\b|\.go\b|\.rs\b|\.cpp\b)",
    re.IGNORECASE,
)
_FILENAME_REWRITE_HINT_RE = re.compile(
    r"(파일|소스|경로|path|이름|filename|확장자|"
    r"\.py\b|\.ts\b|\.tsx\b|\.js\b|\.jsx\b|\.sql\b|\.md\b|\.txt\b|\.json\b|"
    r"\.ya?ml\b|\.csv\b|\.docx\b|\.pptx\b|\.xlsx\b|\.pdf\b|\.hwpx?\b)",
    re.IGNORECASE,
)
_BILINGUAL_EXPANSIONS: dict[str, tuple[str, ...]] = {
    "다이어트": ("diet",),
    "아키텍처": ("architecture",),
    "아침": ("breakfast",),
    "구조": ("architecture", "structure"),
    "브로셔": ("brochure",),
    "검색": ("search", "retrieval"),
    "검색기": ("search", "retrieval"),
    "검색엔진": ("search", "retrieval"),
    "문서": ("document", "docs"),
    "설정": ("config", "configuration"),
    "임베딩": ("embedding", "embeddings"),
    "인덱스": ("index", "indexing"),
    "인덱싱": ("indexing", "index"),
    "음성": ("voice", "audio"),
    "인식": ("recognition",),
    "모델": ("model",),
    "메뉴": ("menu", "meal"),
    "파이프라인": ("pipeline",),
    "오케스트레이터": ("orchestrator",),
    "식단": ("diet", "meal", "menu", "plan"),
    "식단표": ("diet", "meal", "menu", "plan"),
    "점심": ("lunch",),
    "저녁": ("dinner",),
    "거버너": ("governor",),
    "planner": ("query", "intent", "planning"),
    "retrieval": ("search", "fts", "vector"),
    "fts": ("search", "full-text"),
    "vector": ("embedding", "semantic"),
}
_JSON_BLOCK_RE = re.compile(r"\{[\s\S]*\}")


@dataclass(frozen=True)
class QueryAnalysis:
    """Structured analysis of a user query."""

    retrieval_task: str = "document_qa"
    intent: str = "qa"
    sub_intents: list[str] = field(default_factory=list)
    entities: dict[str, object] = field(default_factory=dict)
    search_terms: list[str] = field(default_factory=list)
    target_file: str = ""
    language: str = "ko"
    confidence: float = 0.0
    source: str = "heuristic"

    def to_payload(self) -> dict[str, object]:
        return {
            "retrieval_task": self.retrieval_task,
            "intent": self.intent,
            "sub_intents": list(self.sub_intents),
            "entities": dict(self.entities),
            "search_terms": list(self.search_terms),
            "target_file": self.target_file,
            "language": self.language,
            "confidence": self.confidence,
            "source": self.source,
        }

    @classmethod
    def from_payload(
        cls,
        payload: dict[str, object],
        *,
        fallback: "QueryAnalysis | None" = None,
    ) -> "QueryAnalysis":
        base = fallback or cls()
        retrieval_task = str(payload.get("retrieval_task", base.retrieval_task) or base.retrieval_task)
        intent = str(payload.get("intent", base.intent) or base.intent)
        sub_intents_raw = payload.get("sub_intents", base.sub_intents)
        entities_raw = payload.get("entities", base.entities)
        search_terms_raw = payload.get("search_terms", base.search_terms)

        sub_intents = [
            str(value).strip()
            for value in sub_intents_raw
            if str(value).strip()
        ] if isinstance(sub_intents_raw, list) else list(base.sub_intents)
        entities = dict(entities_raw) if isinstance(entities_raw, dict) else dict(base.entities)
        search_terms = [
            str(value).strip()
            for value in search_terms_raw
            if str(value).strip()
        ] if isinstance(search_terms_raw, list) else list(base.search_terms)

        confidence_raw = payload.get("confidence", base.confidence)
        confidence = base.confidence
        if isinstance(confidence_raw, (int, float)):
            confidence = max(0.0, min(float(confidence_raw), 1.0))

        return cls(
            retrieval_task=retrieval_task,
            intent=intent,
            sub_intents=sub_intents,
            entities=entities,
            search_terms=search_terms,
            target_file=str(payload.get("target_file", base.target_file) or base.target_file),
            language=str(payload.get("language", base.language) or base.language),
            confidence=confidence,
            source=str(payload.get("source", base.source) or base.source),
        )


class LightweightPlannerBackend(Protocol):
    """Optional second-pass planner backend.

    The implementation may be rule-based or model-backed, but it must be
    best-effort only. Baseline heuristic planning remains the source of truth
    when this layer is unavailable or fails.
    """

    def analyze(self, raw_text: str, baseline: QueryAnalysis) -> QueryAnalysis | None:
        """Return an enriched QueryAnalysis or None to keep the baseline."""
        ...


def _detect_language(text: str) -> str:
    korean_chars = len(_KOREAN_RE.findall(text))
    ascii_words = len(_ASCII_RE.findall(text))
    if korean_chars > ascii_words:
        return "ko"
    if ascii_words > 0 and korean_chars == 0:
        return "en"
    if korean_chars > 0 and ascii_words > 0:
        return "mixed"
    return "ko"


def _extract_tokens(raw_text: str) -> list[str]:
    tokens: list[str] = []
    for token in _TOKEN_RE.findall(raw_text):
        cleaned = token.strip(".,?!;:()[]{}\"'").lower()
        if len(cleaned) <= 1 or cleaned in _STOPWORDS:
            continue
        tokens.append(cleaned)
    return tokens


class HeuristicPlanner:
    """Fast deterministic baseline planner."""

    def analyze(self, raw_text: str) -> QueryAnalysis:
        target_file = ""
        if file_matches := _FILENAME_RE.findall(raw_text):
            target_file = file_matches[0]
        elif normalized_matches := _FILENAME_RE.findall(normalize_spoken_code_query(raw_text)):
            target_file = normalized_matches[0]

        tokens = _extract_tokens(raw_text)
        language = _detect_language(raw_text)
        intent = _classify_intent(raw_text, tokens=tokens, target_file=target_file)
        retrieval_task, entities = _classify_retrieval_task(
            raw_text,
            intent=intent,
            target_file=target_file,
            tokens=tokens,
        )
        confidence = 0.45
        if target_file:
            confidence += 0.35
        if len(tokens) >= 2:
            confidence += 0.15
        if language == "mixed":
            confidence -= 0.1
        if intent != "qa":
            confidence = max(confidence, 0.85)
        if retrieval_task != "document_qa":
            confidence = max(confidence, 0.82)

        return QueryAnalysis(
            retrieval_task=retrieval_task,
            intent=intent,
            entities=entities,
            search_terms=tokens,
            target_file=target_file,
            language="ko" if language == "mixed" else language,
            confidence=max(0.0, min(confidence, 0.95)),
            source="heuristic",
        )


class LightweightKeywordExpander:
    """Cheap second-pass enrichment for bilingual and code-adjacent queries.

    This is intentionally lightweight: it does not replace the heuristic
    baseline and does not require the local LLM runtime to be healthy.
    A model-backed backend can later implement the same protocol.
    """

    def analyze(self, raw_text: str, baseline: QueryAnalysis) -> QueryAnalysis | None:
        expanded_terms = list(baseline.search_terms)
        seen = {term.lower() for term in expanded_terms}

        for token in _extract_tokens(raw_text):
            candidates = [token]
            stripped = _strip_topic_suffix(token)
            if stripped != token:
                candidates.append(stripped)
            for candidate in candidates:
                for alias in _BILINGUAL_EXPANSIONS.get(candidate, ()):
                    if alias.lower() not in seen:
                        expanded_terms.append(alias)
                        seen.add(alias.lower())

        if baseline.target_file:
            stem = baseline.target_file.rsplit(".", 1)[0].replace("_", " ").replace("-", " ")
            for token in _extract_tokens(stem):
                if token.lower() not in seen:
                    expanded_terms.append(token)
                    seen.add(token.lower())

        if expanded_terms == baseline.search_terms:
            return None

        return QueryAnalysis(
            retrieval_task=baseline.retrieval_task,
            intent=baseline.intent,
            entities=dict(baseline.entities),
            search_terms=expanded_terms,
            target_file=baseline.target_file,
            language=baseline.language,
            confidence=min(1.0, baseline.confidence + 0.15),
            source="lightweight",
        )


class LLMIntentJSONBackend:
    """Model-backed planner enrichment that returns structured intent JSON.

    This is a best-effort layer. If the backend fails or returns invalid JSON,
    the planner must keep the heuristic baseline.
    """

    def __init__(self, *, llm_backend: object) -> None:
        self._llm_backend = llm_backend

    def analyze(self, raw_text: str, baseline: QueryAnalysis) -> QueryAnalysis | None:
        if self._llm_backend is None or not hasattr(self._llm_backend, "generate"):
            return None

        prompt = self._build_prompt(raw_text, baseline)
        try:
            raw = self._llm_backend.generate(prompt, "", "planner_intent_json")
        except Exception as exc:
            logger.warning("LLM intent planner failed, keeping baseline: %s", exc)
            return None

        payload = self._extract_json_payload(raw)
        if payload is None:
            return None
        return QueryAnalysis.from_payload(payload, fallback=baseline)

    @staticmethod
    def _build_prompt(raw_text: str, baseline: QueryAnalysis) -> str:
        return (
            "다음 사용자 질의를 intent JSON으로만 분류하세요. 설명문 없이 JSON만 출력하세요.\n"
            "필수 필드: retrieval_task, intent, sub_intents, entities, search_terms, target_file, language, confidence, source.\n"
            "intent는 하나의 주 의도만 넣고, 인사말 등 보조 의도는 sub_intents에 넣으세요.\n"
            "retrieval_task는 document_qa, table_lookup, code_lookup, multi_doc_qa, live_data_request, smalltalk 중 하나를 사용하세요.\n"
            "entities에는 day_numbers, meal_slots 같은 구조화 슬롯이 있으면 포함하세요.\n"
            f"baseline={json.dumps(baseline.to_payload(), ensure_ascii=False)}\n"
            f"query={raw_text}"
        )

    @staticmethod
    def _extract_json_payload(raw: str) -> dict[str, object] | None:
        text = raw.strip()
        if text.startswith("```"):
            text = text.strip("`")
            if "\n" in text:
                text = text.split("\n", 1)[1]
        match = _JSON_BLOCK_RE.search(text)
        if match is None:
            return None
        try:
            payload = json.loads(match.group(0))
        except Exception:
            return None
        return payload if isinstance(payload, dict) else None


class Planner:
    """Hybrid planner: heuristic baseline with optional lightweight enrichment.

    Per Spec Section 2.2 PlannerProtocol:
      classify(query) -> str
      build_retrieval_plan(query, intent, ...) -> RetrievalPlan
    """

    def __init__(
        self,
        *,
        model_id: str = "qwen3.5:9b",
        lightweight_backend: LightweightPlannerBackend | object | None = _DEFAULT_LIGHTWEIGHT,
        knowledge_base_path: Path | None = None,
    ) -> None:
        self._model_id = model_id
        self._knowledge_base_path = knowledge_base_path
        self._heuristic = HeuristicPlanner()
        self._keyword_expander = LightweightKeywordExpander()
        if lightweight_backend is _DEFAULT_LIGHTWEIGHT:
            self._lightweight_backend: LightweightPlannerBackend | None = self._keyword_expander
        else:
            self._lightweight_backend = lightweight_backend

    def analyze(self, raw_text: str) -> QueryAnalysis:
        """Analyze a user query using heuristic baseline plus optional enrichment."""
        baseline = self._heuristic.analyze(raw_text)
        normalized_text = self._maybe_normalize_with_identifiers(raw_text, baseline)
        if normalized_text != raw_text:
            baseline = self._heuristic.analyze(normalized_text)
        raw_file_matches = _FILENAME_RE.findall(raw_text)
        if raw_file_matches and not baseline.target_file:
            baseline = QueryAnalysis(
                retrieval_task=baseline.retrieval_task,
                intent=baseline.intent,
                sub_intents=list(baseline.sub_intents),
                entities=dict(baseline.entities),
                search_terms=list(baseline.search_terms),
                target_file=raw_file_matches[0],
                language=baseline.language,
                confidence=baseline.confidence,
                source=baseline.source,
            )
            if baseline.retrieval_task == "code_lookup" and "target_file" not in baseline.entities:
                baseline.entities["target_file"] = raw_file_matches[0]
        if self._lightweight_backend is None:
            return baseline

        if isinstance(self._lightweight_backend, LLMIntentJSONBackend):
            should_use_lightweight = True
        else:
            should_use_lightweight = self._should_use_lightweight(raw_text, baseline)

        if not should_use_lightweight:
            return baseline

        try:
            enriched = self._lightweight_backend.analyze(normalized_text, baseline)
        except Exception as exc:
            logger.warning("Lightweight planner failed, keeping heuristic baseline: %s", exc)
            enriched = None

        result = baseline if enriched is None else self._merge_analysis(baseline, enriched)
        if isinstance(self._lightweight_backend, LLMIntentJSONBackend):
            return self._merge_keyword_expansion(
                raw_text=normalized_text,
                baseline=baseline,
                analysis=result,
            )
        return result

    def _maybe_normalize_with_identifiers(self, raw_text: str, baseline: QueryAnalysis) -> str:
        normalized = raw_text.strip()
        if not normalized:
            return raw_text
        if baseline.target_file:
            return normalize_spoken_code_query(
                raw_text,
                knowledge_base_path=self._knowledge_base_path,
            )
        if baseline.retrieval_task == "code_lookup":
            return normalize_spoken_code_query(
                raw_text,
                knowledge_base_path=self._knowledge_base_path,
            )
        if _CODE_NORMALIZATION_HINT_RE.search(normalized):
            return normalize_spoken_code_query(
                raw_text,
                knowledge_base_path=self._knowledge_base_path,
            )

        rewrite = rewrite_query_with_identifiers(
            raw_text,
            knowledge_base_path=self._knowledge_base_path,
        )
        if _should_apply_filename_rewrite(raw_text, rewrite.candidates):
            return rewrite.rewritten_query
        return raw_text

    def classify_complexity(self, query: str) -> QueryComplexity:
        """Classify query complexity using fast heuristics (no LLM call).

        Returns:
            "simple"  — direct data lookup, single-fact questions (→ fast model)
            "moderate" — standard Q&A, moderate reasoning (→ balanced model)
            "complex" — multi-step analysis, comparison, synthesis (→ deep model)
        """
        return _classify_query_complexity(query)

    @staticmethod
    def _should_use_lightweight(raw_text: str, baseline: QueryAnalysis) -> bool:
        if not raw_text.strip():
            return False
        if baseline.retrieval_task == "table_lookup":
            return True
        if baseline.confidence < 0.7:
            return True
        if _detect_language(raw_text) == "mixed":
            return True
        if baseline.target_file:
            return True
        return _classify_query_complexity(raw_text) == "complex"

    @staticmethod
    def _merge_analysis(baseline: QueryAnalysis, enriched: QueryAnalysis) -> QueryAnalysis:
        search_terms: list[str] = []
        seen: set[str] = set()
        for term in [*baseline.search_terms, *enriched.search_terms]:
            lowered = term.lower()
            if lowered in seen:
                continue
            seen.add(lowered)
            search_terms.append(term)

        return QueryAnalysis(
            retrieval_task=enriched.retrieval_task or baseline.retrieval_task,
            intent=enriched.intent or baseline.intent,
            sub_intents=list(dict.fromkeys([*baseline.sub_intents, *enriched.sub_intents])),
            entities={**baseline.entities, **enriched.entities},
            search_terms=search_terms,
            target_file=enriched.target_file or baseline.target_file,
            language=enriched.language or baseline.language,
            confidence=max(baseline.confidence, enriched.confidence),
            source=enriched.source,
        )

    def _merge_keyword_expansion(
        self,
        *,
        raw_text: str,
        baseline: QueryAnalysis,
        analysis: QueryAnalysis,
    ) -> QueryAnalysis:
        try:
            keyword_enriched = self._keyword_expander.analyze(raw_text, baseline)
        except Exception as exc:
            logger.warning("Keyword planner fallback failed, keeping current analysis: %s", exc)
            return analysis

        if keyword_enriched is None:
            return analysis

        search_terms: list[str] = []
        seen: set[str] = set()
        for term in [*analysis.search_terms, *keyword_enriched.search_terms]:
            lowered = term.lower()
            if lowered in seen:
                continue
            seen.add(lowered)
            search_terms.append(term)

        source = analysis.source
        if analysis.source == baseline.source and search_terms != analysis.search_terms:
            source = keyword_enriched.source

        return QueryAnalysis(
            retrieval_task=analysis.retrieval_task,
            intent=analysis.intent,
            sub_intents=list(analysis.sub_intents),
            entities=dict(analysis.entities),
            search_terms=search_terms,
            target_file=analysis.target_file,
            language=analysis.language,
            confidence=max(analysis.confidence, keyword_enriched.confidence),
            source=source,
        )


def _should_apply_filename_rewrite(raw_text: str, candidates: Sequence[object]) -> bool:
    if not _FILENAME_REWRITE_HINT_RE.search(raw_text):
        return False
    for candidate in candidates:
        if getattr(candidate, "kind", "") != "filename":
            continue
        if float(getattr(candidate, "score", 0.0) or 0.0) >= 0.82:
            return True
    return False


# --- Complexity classification heuristics ---

# Patterns that indicate complex reasoning needs
_COMPLEX_KO = re.compile(
    r"비교|분석|설명해|차이점|장단점|왜\s|이유|추론|요약|종합|평가|"
    r"어떻게\s.*작동|어떤\s.*방법|전략|설계|아키텍처|리팩[토터]|"
    r"최적화|개선|문제점|해결|디버[그깅]|원인",
    re.IGNORECASE,
)
_COMPLEX_EN = re.compile(
    r"compare|analy[sz]e|explain\s+(?:how|why)|difference|pros?\s+(?:and|&)\s+cons?|"
    r"trade.?off|reason|summarize|synthesize|evaluate|strategy|design|architect|"
    r"refactor|optimize|improve|debug|root\s+cause|how\s+does|what\s+are\s+the",
    re.IGNORECASE,
)

# Patterns that indicate simple lookups
_SIMPLE_KO = re.compile(
    r"^.{0,20}(?:뭐|무엇|어디|누구|언제|몇|얼마)\s*(?:야|이야|인가|입니까|예요|에요)?\s*\??$|"
    r"알려\s*줘|찾아\s*줘|보여\s*줘|있어\??$",
    re.IGNORECASE,
)
_SIMPLE_EN = re.compile(
    r"^(?:what\s+is|where\s+is|who\s+is|when\s+(?:is|was|did)|how\s+many|how\s+much|"
    r"list|show|find|get|look\s+up)\b",
    re.IGNORECASE,
)


def _classify_query_complexity(query: str) -> QueryComplexity:
    """Heuristic complexity classifier. Fast, deterministic, no LLM."""
    q = query.strip()

    # Very short queries are simple lookups
    if len(q) < 15:
        return "simple"

    # Check for complex indicators first (higher priority)
    if _COMPLEX_KO.search(q) or _COMPLEX_EN.search(q):
        return "complex"

    # Check for simple lookup patterns
    if _SIMPLE_KO.search(q) or _SIMPLE_EN.search(q):
        return "simple"

    # Default: moderate for medium-length, simple for short
    if len(q) > 60:
        return "moderate"
    return "simple"


def _classify_intent(raw_text: str, *, tokens: list[str], target_file: str) -> str:
    normalized = raw_text.strip()
    lowered = normalized.lower()
    informational_markers = (
        "파일", "문서", "코드", ".py", ".ts", ".js",
        "검색", "찾아", "요약", "정리", "설명", "알려",
        "메뉴", "식단", "날씨", "기온", "비", "눈",
        "지하철", "버스", "경로", "길찾기", "가는 길", "가는길",
    )
    if target_file:
        return "qa"
    if _SMALLTALK_GREETING_RE.search(normalized) or _SMALLTALK_POLITE_RE.search(normalized):
        if not any(marker in lowered for marker in informational_markers):
            return "smalltalk"
    if _contains_non_negated_match(normalized, _WEATHER_RE):
        return "weather"
    if any(token in lowered for token in ("지하철", "버스", "경로", "길찾기", "가는 길", "가는길")):
        return "route_guidance"
    # Action intent: verbs like 열어줘, 켜줘, open, launch
    if _ACTION_VERB_RE.search(raw_text):
        return "action"

    return "qa"


def _classify_retrieval_task(
    raw_text: str,
    *,
    intent: str,
    target_file: str,
    tokens: list[str],
) -> tuple[str, dict[str, object]]:
    normalized = raw_text.strip()
    lowered = normalized.lower()
    entities: dict[str, object] = {}
    filename_match = _FILENAME_RE.search(normalized)
    resolved_target_file = target_file or (filename_match.group(1) if filename_match else "")

    if intent == "smalltalk":
        return "smalltalk", entities

    if intent == "action":
        return "action_request", entities

    if intent == "weather":
        return "live_data_request", {"capability": "weather"}

    if any(term in lowered for term in ("오늘 일정", "캘린더", "calendar", "일정")):
        return "live_data_request", {"capability": "calendar"}

    row_ids = re.findall(r"(\d+)\s*(?:일\s*차|일차|day|번)", normalized, re.IGNORECASE)
    meal_slots = _extract_meal_slots(lowered)
    if any(term in lowered for term in ("식단표", "식단", "메뉴")) or meal_slots:
        if row_ids:
            entities["row_ids"] = row_ids
        if meal_slots:
            entities["fields"] = meal_slots
        return "table_lookup", entities

    if resolved_target_file:
        if Path(resolved_target_file).suffix.lower() in {".py", ".ts", ".tsx", ".js", ".jsx", ".sql", ".java", ".kt", ".go", ".rs", ".cpp", ".c", ".h"}:
            return "code_lookup", {"target_file": resolved_target_file}
        return "document_qa", {"document": Path(resolved_target_file).name}

    if any(term in lowered for term in ("소스", "코드", "클래스", "함수", "메서드", ".py", ".ts", ".js")):
        return "code_lookup", {}

    if any(term in lowered for term in ("문서", "파일형식", "형식", "자료 구조", "기본 구조", "설명")):
        topic_terms = _extract_document_topic_terms(normalized, tokens)
        negated_terms = _extract_negated_terms(normalized)
        if negated_terms:
            topic_terms = [
                term for term in topic_terms
                if not any(_topic_overlaps_negative(term, negated) for negated in negated_terms)
            ]
        if topic_terms:
            entities["topic_terms"] = topic_terms[:6]
        if negated_terms:
            entities["negative_terms"] = negated_terms[:4]
        return "document_qa", entities

    return "document_qa", entities


def _extract_meal_slots(lowered: str) -> list[str]:
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
    return matched_fields


def _contains_non_negated_match(text: str, pattern: re.Pattern[str]) -> bool:
    for match in pattern.finditer(text):
        suffix = text[match.end():match.end() + 8]
        if _NEGATION_SUFFIX_RE.match(suffix.strip()):
            continue
        return True
    return False


def _extract_document_topic_terms(raw_text: str, tokens: list[str]) -> list[str]:
    cleaned_tokens = []
    seen = set()
    for token in tokens:
        normalized_token = _strip_topic_suffix(token.strip())
        compact = normalized_token.lower()
        if compact in _DOCUMENT_TOPIC_STOPWORDS or len(compact) < 2:
            continue
        cleaned_tokens.append(normalized_token)

    phrases: list[str] = []
    raw_compact = " ".join(raw_text.split())
    bigrams: list[str] = []
    for index in range(0, len(cleaned_tokens) - 1):
        phrase = " ".join(cleaned_tokens[index:index + 2]).strip()
        compact = phrase.replace(" ", "")
        if len(compact) < 4:
            continue
        if phrase not in bigrams and (phrase in raw_compact or compact in raw_text.replace(" ", "")):
            bigrams.append(phrase)
    for size in (3, 2):
        for index in range(0, len(cleaned_tokens) - size + 1):
            phrase = " ".join(cleaned_tokens[index:index + size]).strip()
            compact = phrase.replace(" ", "")
            if len(compact) < 4:
                continue
            if phrase in phrases:
                continue
            if phrase in raw_compact or compact in raw_text.replace(" ", ""):
                phrases.append(phrase)

    prioritized = []
    for phrase in bigrams:
        if any(keyword in phrase for keyword in ("기본 구조", "자료 구조", "저장 구조", "그리기 개체", "하이퍼 텍스트", "파일 형식", "파일형식")):
            prioritized.append(phrase)
    for phrase in phrases:
        if any(keyword in phrase for keyword in ("기본 구조", "자료 구조", "저장 구조", "개체", "형식")):
            if phrase not in prioritized:
                prioritized.append(phrase)
    for token in cleaned_tokens:
        if token not in prioritized:
            prioritized.append(token)
    deduped: list[str] = []
    for item in prioritized:
        lowered = item.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        deduped.append(item)
    return deduped


def _extract_negated_terms(raw_text: str) -> list[str]:
    patterns = [
        re.compile(r"([A-Za-z0-9가-힣\s]{2,30}?)\s*말고"),
        re.compile(r"([A-Za-z0-9가-힣\s]{2,30}?)\s*아니라"),
    ]
    terms: list[str] = []
    for pattern in patterns:
        for match in pattern.finditer(raw_text):
            parts = [_strip_topic_suffix(part) for part in match.group(1).split()]
            parts = [part for part in parts if part and part.lower() not in _DOCUMENT_TOPIC_STOPWORDS]
            if len(parts) > 3:
                parts = parts[-3:]
            phrase = " ".join(parts).strip()
            if len(phrase) < 2:
                continue
            if phrase not in terms:
                terms.append(phrase)
    return terms


def _strip_topic_suffix(token: str) -> str:
    for suffix in _TOPIC_SUFFIXES:
        if token.endswith(suffix) and len(token) > len(suffix) + 1:
            return token[: -len(suffix)]
    return token


def _topic_overlaps_negative(topic: str, negative: str) -> bool:
    topic_tokens = {part for part in topic.split() if part}
    negative_tokens = {part for part in negative.split() if part}
    if not topic_tokens or not negative_tokens:
        return False
    return topic_tokens.issubset(negative_tokens) or bool(topic_tokens & negative_tokens and len(topic_tokens) <= 2)
