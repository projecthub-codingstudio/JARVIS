"""EvidenceBuilder — builds verified evidence sets from ranked search results.

When db is provided, resolves chunk text and verifies citation freshness.
Without db, falls back to stub behavior for backward compatibility.

Per Spec Section 11.2:
  - Applies freshness score boost for recently modified files
  - STALE auto-detection via content hash comparison
  - STALE/MISSING citations are included but flagged for warning display

Score boosting:
  - Freshness boost: recently modified files rank higher
  - Filename match boost: documents matching query filename terms rank higher
  - Identifier match boost: chunks containing code identifiers from query rank higher
"""
from __future__ import annotations

import re
import sqlite3
import time
from pathlib import Path
from typing import Sequence

from jarvis.contracts import (
    CitationRecord,
    CitationState,
    DocumentRecord,
    EvidenceItem,
    HybridSearchResult,
    IndexingStatus,
    TypedQueryFragment,
    VerifiedEvidenceSet,
)
from jarvis.retrieval.freshness import FreshnessChecker
from jarvis.observability.metrics import MetricName, MetricsCollector


# Patterns for extracting specific identifiers from queries
_FILENAME_RE = re.compile(r"[\w.-]+\.(?:py|ts|tsx|js|jsx|sql|md|txt|json|yaml|yml|csv|docx|pptx|xlsx|pdf)")
# Also match filenames without extension (e.g., "14day_diet_supplements_final")
_FILENAME_STEM_RE = re.compile(r"\b([a-zA-Z0-9][\w-]{5,}(?:_[\w-]+)+)\b")
_CODE_IDENT_RE = re.compile(r"[a-zA-Z_]\w{3,}(?:\.\w+)*")  # function/class names like _build_foo, MyClass

# Boost values
_FILENAME_MATCH_BOOST = 0.20   # document path contains queried filename
_FILENAME_STEM_BOOST = 0.15    # document stem matches without extension
_IDENTIFIER_MATCH_BOOST = 0.08  # chunk text contains queried code identifier
_ROW_NUMBER_MATCH_BOOST = 0.25  # chunk contains exact row number from query (e.g., Day=9)
_CODE_SOURCE_BOOST = 0.28
_NON_CODE_PENALTY = 0.14
_CLASS_SIGNATURE_BOOST = 0.16
_FUNCTION_SIGNATURE_BOOST = 0.12
_DOCUMENT_PHRASE_BOOST = 0.18
_DOCUMENT_EXPLANATORY_BOOST = 0.10
_DOCUMENT_REFERENCE_PENALTY = 0.12
MIN_RELEVANCE_SCORE = 0.01     # lowered: RRF scores are inherently small (~0.016)

# Pattern to extract numbers referenced in queries (e.g., "9일차", "day 5", "13일")
_QUERY_NUMBER_RE = re.compile(r"(\d+)\s*(?:일\s*차|일차|일|번째|day|번)", re.IGNORECASE)
_CLASS_QUERY_RE = re.compile(r"(클래스|class)", re.IGNORECASE)
_FUNCTION_QUERY_RE = re.compile(r"(함수|메서드|메소드|function|method)", re.IGNORECASE)
_CODE_QUERY_RE = re.compile(
    r"(소스|코드|파이(?:썬|선)|python|class|클래스|function|함수|method|메서드|def\s|import\s|\.py\b|source)",
    re.IGNORECASE,
)
_CODE_EXTENSIONS = {".py", ".ts", ".tsx", ".js", ".jsx", ".sql", ".java", ".kt", ".go", ".rs", ".cpp", ".c", ".h"}
_DOCUMENT_EXPLANATORY_RE = re.compile(r"(?:이다|있다|한다|된다|저장된다|구조로|의미|설명)")
_DOCUMENT_REFERENCE_RE = re.compile(r"(?:참조|자세한 것은|보기 바란다|아닐 때는)")
_PHRASE_TOKEN_RE = re.compile(r"[A-Za-z0-9가-힣]+")
_PHRASE_STOPWORDS = {
    "설명", "설명해", "설명해요", "설명해줘", "설명해주세요", "주세요",
    "문서", "자료", "중", "중에", "대해", "대해서", "기본", "구조",
}


class EvidenceBuilder:
    """Builds VerifiedEvidenceSet from hybrid search results."""

    def __init__(
        self,
        *,
        db: sqlite3.Connection | None = None,
        metrics: MetricsCollector | None = None,
    ) -> None:
        self._db = db
        self._freshness = FreshnessChecker()
        self._metrics = metrics

    def build(
        self,
        results: Sequence[HybridSearchResult],
        fragments: Sequence[TypedQueryFragment],
    ) -> VerifiedEvidenceSet:
        started_at = time.perf_counter()
        if not results:
            return VerifiedEvidenceSet(items=(), query_fragments=tuple(fragments))

        if self._db is None:
            return VerifiedEvidenceSet(items=(), query_fragments=tuple(fragments))

        # Extract filename and identifier terms from query for boost scoring
        query_text = " ".join(f.text for f in fragments)
        query_filenames = {m.lower() for m in _FILENAME_RE.findall(query_text)}
        query_filename_stems = {m.lower() for m in _FILENAME_STEM_RE.findall(query_text)}
        query_identifiers = {m for m in _CODE_IDENT_RE.findall(query_text) if len(m) > 4}
        prefers_code = _looks_like_code_query(query_text)
        wants_class = bool(_CLASS_QUERY_RE.search(query_text))
        wants_function = bool(_FUNCTION_QUERY_RE.search(query_text))
        query_phrases = _document_query_phrases(query_text)

        items: list[EvidenceItem] = []
        for i, result in enumerate(results, 1):
            chunk_row = self._db.execute(
                "SELECT text, heading_path FROM chunks WHERE chunk_id = ?",
                (result.chunk_id,),
            ).fetchone()
            if chunk_row is None:
                continue

            doc_row = self._db.execute(
                "SELECT document_id, path, content_hash, size_bytes, indexing_status"
                " FROM documents WHERE document_id = ?",
                (result.document_id,),
            ).fetchone()
            if doc_row is None:
                continue

            doc = DocumentRecord(
                document_id=doc_row[0],
                path=doc_row[1],
                content_hash=doc_row[2],
                size_bytes=doc_row[3],
                indexing_status=IndexingStatus(doc_row[4]),
            )

            citation = CitationRecord(
                document_id=result.document_id,
                chunk_id=result.chunk_id,
                label=f"[{i}]",
                state=CitationState.VALID,
            )
            citation = self._freshness.refresh_citation(citation, doc)

            # --- Score boosting ---
            boost = 0.0

            # Freshness boost: recently modified files rank higher
            boost += self._freshness.compute_freshness_boost(doc)

            # Filename match boost: document path contains queried filename
            if doc.path:
                doc_filename = Path(doc.path).name.lower()
                doc_stem = Path(doc.path).stem.lower()
                if query_filenames and doc_filename in query_filenames:
                    boost += _FILENAME_MATCH_BOOST
                elif query_filename_stems and doc_stem in query_filename_stems:
                    boost += _FILENAME_STEM_BOOST
                else:
                    # Fuzzy: check if query words match document stem tokens
                    # e.g., "14day diet supplements final" matches "14day_diet_supplements_final"
                    stem_tokens = set(doc_stem.replace("-", "_").split("_"))
                    query_words = {w.lower() for f in fragments for w in f.text.split() if len(w) > 2}
                    overlap = stem_tokens & query_words
                    if len(overlap) >= 2 and len(overlap) >= len(stem_tokens) * 0.5:
                        boost += _FILENAME_STEM_BOOST
                if prefers_code:
                    if _is_code_path(doc.path):
                        boost += _CODE_SOURCE_BOOST
                    else:
                        boost -= _NON_CODE_PENALTY

            # Identifier match boost: chunk contains queried code identifier
            chunk_text = chunk_row[0] if chunk_row[0] else ""
            if query_identifiers and chunk_text:
                for ident in query_identifiers:
                    if ident in chunk_text:
                        boost += _IDENTIFIER_MATCH_BOOST
                        break  # One boost per chunk
            if chunk_text and wants_class and any(
                re.search(rf"\bclass\s+{re.escape(ident)}\b", chunk_text)
                for ident in query_identifiers
            ):
                boost += _CLASS_SIGNATURE_BOOST
            if chunk_text and wants_function and any(
                re.search(rf"\b(?:def|function)\s+{re.escape(ident)}\b", chunk_text)
                for ident in query_identifiers
            ):
                boost += _FUNCTION_SIGNATURE_BOOST
            if not prefers_code and chunk_text:
                boost += _document_chunk_boost(
                    query_text=query_text,
                    query_phrases=query_phrases,
                    heading_path=chunk_row[1] if len(chunk_row) > 1 and chunk_row[1] else "",
                    chunk_text=chunk_text,
                )

            # Row number match boost: query mentions a specific number (e.g., "9일차")
            # and chunk contains that exact row (e.g., "Day=9 |")
            query_numbers = _QUERY_NUMBER_RE.findall(query_text)
            if query_numbers and chunk_text:
                for num in query_numbers:
                    # Match table row patterns: "Day=N", "N |", row-N
                    if (f"Day={num} " in chunk_text
                            or f"Day={num}|" in chunk_text
                            or f"={num} |" in chunk_text
                            or f"row-{num}" in chunk_text.lower()):
                        boost += _ROW_NUMBER_MATCH_BOOST
                        break

            boosted_score = result.rrf_score + boost

            text = chunk_text or result.snippet
            heading_path = chunk_row[1] if len(chunk_row) > 1 and chunk_row[1] else ""
            items.append(EvidenceItem(
                chunk_id=result.chunk_id,
                document_id=result.document_id,
                text=text,
                citation=citation,
                relevance_score=boosted_score,
                source_path=doc.path,
                heading_path=heading_path,
            ))

        # Re-sort by boosted score (boosts may reorder results)
        items.sort(key=lambda x: x.relevance_score, reverse=True)

        evidence = VerifiedEvidenceSet(
            items=tuple(items), query_fragments=tuple(fragments)
        )
        if self._metrics is not None:
            total = len(evidence.items)
            missing = sum(1 for item in evidence.items if item.citation.state == CitationState.MISSING)
            stale = sum(1 for item in evidence.items if item.citation.state == CitationState.STALE)
            self._metrics.record(
                MetricName.RETRIEVAL_TOP5_HIT,
                1.0 if total > 0 else 0.0,
                unit="ratio",
                tags={"top_k": str(min(5, total))},
            )
            self._metrics.record(
                MetricName.CITATION_MISSING_RATE,
                (missing / total) if total else 0.0,
                unit="ratio",
            )
            self._metrics.record(
                MetricName.CITATION_STALE_RATE,
                (stale / total) if total else 0.0,
                unit="ratio",
            )
            self._metrics.record(
                MetricName.TRUST_RECOVERY_TIME_MS,
                (time.perf_counter() - started_at) * 1000,
                tags={"items": str(total)},
            )
        return evidence


def _looks_like_code_query(query_text: str) -> bool:
    return bool(_CODE_QUERY_RE.search(query_text))


def _document_query_phrases(query_text: str) -> tuple[str, ...]:
    tokens = [token for token in _PHRASE_TOKEN_RE.findall(query_text) if len(token) >= 2]
    phrases: list[str] = []
    for size in range(2, min(4, len(tokens)) + 1):
        for index in range(0, len(tokens) - size + 1):
            phrase = " ".join(tokens[index:index + size]).strip()
            compact = phrase.replace(" ", "")
            if compact in _PHRASE_STOPWORDS:
                continue
            if len(compact) < 4:
                continue
            if phrase not in phrases:
                phrases.append(phrase)
    return tuple(phrases)


def _document_chunk_boost(
    *,
    query_text: str,
    query_phrases: tuple[str, ...],
    heading_path: str,
    chunk_text: str,
) -> float:
    boost = 0.0
    normalized_chunk = " ".join(chunk_text.split())
    compact_chunk = normalized_chunk.replace(" ", "")

    phrase_matches = 0
    for phrase in query_phrases:
        compact_phrase = phrase.replace(" ", "")
        if compact_phrase and compact_phrase in compact_chunk:
            phrase_matches += 1
    if phrase_matches:
        boost += _DOCUMENT_PHRASE_BOOST * min(2, phrase_matches)

    heading_lower = heading_path.lower()
    if "table-row" not in heading_lower and "table-summary" not in heading_lower:
        if _DOCUMENT_EXPLANATORY_RE.search(normalized_chunk):
            boost += _DOCUMENT_EXPLANATORY_BOOST
        if _DOCUMENT_REFERENCE_RE.search(normalized_chunk) and phrase_matches == 0:
            boost -= _DOCUMENT_REFERENCE_PENALTY

    if "기본 구조" in query_text and "기본 구조" in normalized_chunk:
        boost += _DOCUMENT_PHRASE_BOOST

    return boost


def _is_code_path(path: str) -> bool:
    return Path(path).suffix.lower() in _CODE_EXTENSIONS
