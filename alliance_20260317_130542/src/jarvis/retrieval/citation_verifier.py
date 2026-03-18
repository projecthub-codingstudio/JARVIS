"""Sentence-level citation verification for grounded answers."""

from __future__ import annotations

import re
from pathlib import Path

from jarvis.contracts import VerifiedEvidenceSet

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?。！？])\s+|\n+")
_TOKEN_RE = re.compile(r"[0-9A-Za-z가-힣_./-]+")
_CITATION_RE = re.compile(r"\[\d+\]")


def _tokenize(text: str) -> set[str]:
    return {
        token.lower()
        for token in _TOKEN_RE.findall(text)
        if len(token) >= 2 and not token.isdigit()
    }


class CitationVerifier:
    """Conservative verifier that flags unsupported factual sentences.

    The verifier is intentionally simple: it only warns when a sentence does not
    cite a label directly and also lacks enough lexical overlap with any
    retrieved evidence item.
    """

    def verify(self, answer_text: str, evidence: VerifiedEvidenceSet) -> tuple[str, ...]:
        if not answer_text.strip() or evidence.is_empty:
            return ()

        evidence_token_sets: list[set[str]] = []
        for item in evidence.items:
            tokens = _tokenize(item.text)
            if item.source_path:
                tokens.update(_tokenize(Path(item.source_path).name))
            evidence_token_sets.append(tokens)

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

            supported = False
            for evidence_tokens in evidence_token_sets:
                overlap = sentence_tokens & evidence_tokens
                if len(overlap) >= 2:
                    supported = True
                    break

            if not supported:
                shortened = sentence[:120] + "..." if len(sentence) > 120 else sentence
                warnings.append(f"근거 정렬 미확인 문장: {shortened}")

        return tuple(warnings)
