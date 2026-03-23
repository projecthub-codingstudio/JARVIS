"""Planner — AI-based intent classification and query normalization.

Per Spec Section 2.1/2.2:
  - classify(query) -> intent type
  - build_retrieval_plan(query, intent) -> normalized search keywords
  - classify_complexity(query) -> "simple" | "moderate" | "complex"

Uses the LLM backend to analyze user queries and extract structured
search terms, handling Korean→English translation for mixed-language
knowledge bases.
"""

from __future__ import annotations

import json
import logging
import re
import urllib.request
import urllib.error
from dataclasses import dataclass, field
from typing import Literal

logger = logging.getLogger(__name__)

QueryComplexity = Literal["simple", "moderate", "complex"]

_OLLAMA_BASE = "http://localhost:11434"

_ANALYSIS_PROMPT = """Extract search keywords from this question. Include both Korean and English translations.
Respond ONLY with JSON: {"keywords_ko": [...], "keywords_en": [...], "target_file": "..."}

Question: """


@dataclass(frozen=True)
class QueryAnalysis:
    """Structured analysis of a user query."""

    intent: str = "qa"
    search_terms: list[str] = field(default_factory=list)
    target_file: str = ""
    language: str = "ko"


class Planner:
    """AI-based query analyzer and search planner.

    Per Spec Section 2.2 PlannerProtocol:
      classify(query) -> str
      build_retrieval_plan(query, intent, ...) -> RetrievalPlan
    """

    def __init__(self, *, model_id: str = "qwen3:30b-a3b") -> None:
        self._model_id = model_id
        self._ollama_available: bool | None = None

    def analyze(self, raw_text: str) -> QueryAnalysis:
        """Analyze a user query using LLM to extract search terms and intent.

        Returns structured QueryAnalysis with bilingual search terms.
        Falls back to simple whitespace splitting if LLM is unavailable.
        """
        # Skip Ollama if previously unavailable (avoid repeated connection errors)
        if self._ollama_available is False:
            return self._fallback_analyze(raw_text)
        try:
            result = self._llm_analyze(raw_text)
            self._ollama_available = True
            return result
        except Exception as e:
            self._ollama_available = False
            logger.warning("LLM analysis failed: %s — using fallback (will not retry)", e)
            return self._fallback_analyze(raw_text)

    def _llm_analyze(self, raw_text: str) -> QueryAnalysis:
        """Use Ollama LLM to analyze the query."""
        payload = json.dumps({
            "model": self._model_id,
            "prompt": _ANALYSIS_PROMPT + raw_text,
            "stream": False,
            "options": {
                "temperature": 0.1,
                "num_predict": 256,
            },
        }).encode()

        req = urllib.request.Request(
            f"{_OLLAMA_BASE}/api/generate",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode())

        response_text = result.get("response", "")
        return self._parse_response(response_text, raw_text)

    def _parse_response(self, response_text: str, raw_text: str) -> QueryAnalysis:
        """Parse LLM JSON response into QueryAnalysis."""
        # Extract JSON from response (may have markdown fences)
        text = response_text.strip()
        if "```" in text:
            # Extract from code block
            parts = text.split("```")
            for part in parts:
                part = part.strip()
                if part.startswith("json"):
                    part = part[4:].strip()
                if part.startswith("{"):
                    text = part
                    break

        # Find JSON object
        start = text.find("{")
        end = text.rfind("}") + 1
        if start == -1 or end == 0:
            return self._fallback_analyze(raw_text)

        data = json.loads(text[start:end])

        # Combine Korean and English terms
        terms = []
        for t in data.get("keywords_ko", data.get("search_terms_original", [])):
            if t and t not in terms:
                terms.append(t)
        for t in data.get("keywords_en", data.get("search_terms_translated", [])):
            if t and t not in terms:
                terms.append(t)

        # Add target file as a search term if specified
        target = data.get("target_file", "")

        return QueryAnalysis(
            intent=data.get("intent", "qa"),
            search_terms=terms,
            target_file=target,
            language=data.get("language", "ko"),
        )

    def _fallback_analyze(self, raw_text: str) -> QueryAnalysis:
        """Simple fallback: whitespace split."""
        terms = [w for w in raw_text.split() if len(w) > 1]
        return QueryAnalysis(
            intent="qa",
            search_terms=terms,
            language="ko",
        )

    def classify_complexity(self, query: str) -> QueryComplexity:
        """Classify query complexity using fast heuristics (no LLM call).

        Returns:
            "simple"  — direct data lookup, single-fact questions (→ fast model)
            "moderate" — standard Q&A, moderate reasoning (→ balanced model)
            "complex" — multi-step analysis, comparison, synthesis (→ deep model)
        """
        return _classify_query_complexity(query)


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
