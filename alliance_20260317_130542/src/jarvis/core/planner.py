"""Planner — AI-based intent classification and query normalization.

Per Spec Section 2.1/2.2:
  - classify(query) -> intent type
  - build_retrieval_plan(query, intent) -> normalized search keywords

Uses the LLM backend to analyze user queries and extract structured
search terms, handling Korean→English translation for mixed-language
knowledge bases.
"""

from __future__ import annotations

import json
import logging
import urllib.request
import urllib.error
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

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

    def analyze(self, raw_text: str) -> QueryAnalysis:
        """Analyze a user query using LLM to extract search terms and intent.

        Returns structured QueryAnalysis with bilingual search terms.
        Falls back to simple whitespace splitting if LLM is unavailable.
        """
        try:
            return self._llm_analyze(raw_text)
        except Exception as e:
            logger.warning("LLM analysis failed: %s — using fallback", e)
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
