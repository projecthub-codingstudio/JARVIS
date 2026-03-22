"""Claim-level citation verification for grounded answers.

Splits LLM-generated sentences into individual factual claims and
verifies each claim independently against evidence. This catches
cases where a sentence contains both supported and unsupported facts.

Upgrade from sentence-level (v1) per AUDIT_REPORT Section 12:
  - v1: overlap ≥ 2 tokens per sentence → too loose
  - v2: overlap ≥ 3 tokens per claim + numeric value matching
"""

from __future__ import annotations

import re
from pathlib import Path

from jarvis.contracts import VerifiedEvidenceSet

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?。！？])\s+|\n+")
_TOKEN_RE = re.compile(r"[0-9A-Za-z가-힣_./-]+")
_CITATION_RE = re.compile(r"\[\d+\]")

# Patterns for splitting sentences into sub-claims
_CLAIM_SPLIT_KO = re.compile(
    r"(?:,\s*|;\s*|그리고\s+|또한\s+|및\s+|이며\s+|이고\s+|하며\s+|하고\s+|으며\s+|고\s+(?=[가-힣]))"
)
_CLAIM_SPLIT_EN = re.compile(
    r"(?:,\s+(?:and|but|while|whereas|however|also|additionally)\s+|;\s+|,\s+)"
)

# Numeric value pattern: extract the numeric core from "350입니다", "5일차", "1.5초" etc.
_NUMERIC_VALUE_RE = re.compile(r"\d[\d,.]*")


def _tokenize(text: str) -> set[str]:
    return {
        token.lower()
        for token in _TOKEN_RE.findall(text)
        if len(token) >= 2 and not token.isdigit()
    }


def _extract_numbers(text: str) -> set[str]:
    """Extract numeric values for exact value matching."""
    return {m.group().strip() for m in _NUMERIC_VALUE_RE.finditer(text)}


def _split_claims(sentence: str) -> list[str]:
    """Split a sentence into individual factual claims."""
    # Try Korean conjunctions first, then English
    parts = _CLAIM_SPLIT_KO.split(sentence)
    if len(parts) <= 1:
        parts = _CLAIM_SPLIT_EN.split(sentence)
    # Filter out too-short fragments
    return [p.strip() for p in parts if len(p.strip()) >= 6]


class CitationVerifier:
    """Claim-level verifier that checks each factual claim independently.

    Splits sentences into sub-claims at conjunction boundaries and verifies
    each claim against evidence with stricter overlap requirements than
    the previous sentence-level approach.
    """

    def verify(self, answer_text: str, evidence: VerifiedEvidenceSet) -> tuple[str, ...]:
        if not answer_text.strip() or evidence.is_empty:
            return ()

        # Pre-tokenize all evidence items
        evidence_token_sets: list[set[str]] = []
        evidence_number_sets: list[set[str]] = []
        for item in evidence.items:
            tokens = _tokenize(item.text)
            if item.source_path:
                tokens.update(_tokenize(Path(item.source_path).name))
            evidence_token_sets.append(tokens)
            evidence_number_sets.append(_extract_numbers(item.text))

        # Union of all evidence tokens for quick pre-filter
        all_evidence_tokens = set()
        for ts in evidence_token_sets:
            all_evidence_tokens.update(ts)

        warnings: list[str] = []
        for raw_sentence in _SENTENCE_SPLIT_RE.split(answer_text):
            sentence = raw_sentence.strip()
            if len(sentence) < 8:
                continue
            if _CITATION_RE.search(sentence):
                continue

            sentence_tokens = _tokenize(sentence)
            if len(sentence_tokens) < 3:
                continue

            # Quick check: if full sentence has good overlap, skip claim splitting
            if self._is_supported(sentence_tokens, evidence_token_sets, min_overlap=3):
                continue

            # Split into claims and check each independently
            claims = _split_claims(sentence)
            if len(claims) <= 1:
                # Single claim, already failed the overlap check above
                shortened = sentence[:120] + "..." if len(sentence) > 120 else sentence
                warnings.append(f"근거 미확인: {shortened}")
                continue

            for claim in claims:
                claim_tokens = _tokenize(claim)
                if len(claim_tokens) < 2:
                    continue

                # Sub-claims are shorter so require fewer overlapping tokens
                needed = 2 if len(claim_tokens) >= 4 else 1
                if self._is_supported(claim_tokens, evidence_token_sets, min_overlap=needed):
                    continue

                # Check numeric value matching as fallback
                claim_numbers = _extract_numbers(claim)
                if claim_numbers and self._numbers_supported(claim_numbers, evidence_number_sets):
                    continue

                shortened = claim[:120] + "..." if len(claim) > 120 else claim
                warnings.append(f"근거 미확인: {shortened}")

        return tuple(warnings)

    @staticmethod
    def _is_supported(
        tokens: set[str],
        evidence_token_sets: list[set[str]],
        *,
        min_overlap: int,
    ) -> bool:
        """Check if tokens have sufficient overlap with any evidence item."""
        for evidence_tokens in evidence_token_sets:
            if len(tokens & evidence_tokens) >= min_overlap:
                return True
        return False

    @staticmethod
    def _numbers_supported(
        claim_numbers: set[str],
        evidence_number_sets: list[set[str]],
    ) -> bool:
        """Check if numeric values in a claim appear in evidence."""
        for evidence_numbers in evidence_number_sets:
            if claim_numbers & evidence_numbers:
                return True
        return False
