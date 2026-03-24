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
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Protocol

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
_STOPWORDS = {
    "the", "a", "an", "is", "are", "to", "for", "of", "and", "or", "what", "how",
    "알려줘", "알려주세요", "보여줘", "보여주세요", "찾아줘", "찾아주세요",
    "설명해줘", "설명해주세요", "무엇", "뭐", "어디", "누구", "언제", "몇", "얼마",
}
_BILINGUAL_EXPANSIONS: dict[str, tuple[str, ...]] = {
    "아키텍처": ("architecture",),
    "구조": ("architecture", "structure"),
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
    "파이프라인": ("pipeline",),
    "오케스트레이터": ("orchestrator",),
    "거버너": ("governor",),
    "planner": ("query", "intent", "planning"),
    "retrieval": ("search", "fts", "vector"),
    "fts": ("search", "full-text"),
    "vector": ("embedding", "semantic"),
}


@dataclass(frozen=True)
class QueryAnalysis:
    """Structured analysis of a user query."""

    intent: str = "qa"
    search_terms: list[str] = field(default_factory=list)
    target_file: str = ""
    language: str = "ko"
    confidence: float = 0.0
    source: str = "heuristic"


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

        tokens = _extract_tokens(raw_text)
        language = _detect_language(raw_text)
        confidence = 0.45
        if target_file:
            confidence += 0.35
        if len(tokens) >= 2:
            confidence += 0.15
        if language == "mixed":
            confidence -= 0.1

        return QueryAnalysis(
            intent="qa",
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
            for alias in _BILINGUAL_EXPANSIONS.get(token, ()):
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
            intent=baseline.intent,
            search_terms=expanded_terms,
            target_file=baseline.target_file,
            language=baseline.language,
            confidence=min(1.0, baseline.confidence + 0.15),
            source="lightweight",
        )


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
        if lightweight_backend is _DEFAULT_LIGHTWEIGHT:
            self._lightweight_backend: LightweightPlannerBackend | None = LightweightKeywordExpander()
        else:
            self._lightweight_backend = lightweight_backend

    def analyze(self, raw_text: str) -> QueryAnalysis:
        """Analyze a user query using heuristic baseline plus optional enrichment."""
        normalized_text = normalize_spoken_code_query(
            raw_text,
            knowledge_base_path=self._knowledge_base_path,
        )
        baseline = self._heuristic.analyze(normalized_text)
        if self._lightweight_backend is None or not self._should_use_lightweight(normalized_text, baseline):
            return baseline

        try:
            enriched = self._lightweight_backend.analyze(normalized_text, baseline)
        except Exception as exc:
            logger.warning("Lightweight planner failed, keeping heuristic baseline: %s", exc)
            return baseline

        if enriched is None:
            return baseline
        return self._merge_analysis(baseline, enriched)

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
            intent=enriched.intent or baseline.intent,
            search_terms=search_terms,
            target_file=enriched.target_file or baseline.target_file,
            language=enriched.language or baseline.language,
            confidence=max(baseline.confidence, enriched.confidence),
            source=enriched.source,
        )


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
