"""Retrieval strategy selection and task-specific candidate augmentation."""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Protocol

from jarvis.contracts import HybridSearchResult, SearchHit, TypedQueryFragment, VectorHit
from jarvis.core.planner import QueryAnalysis, _BILINGUAL_EXPANSIONS, _strip_topic_suffix

_ROW_ID_RE = re.compile(r"(\d+)\s*(?:일\s*차|일차|day|번)", re.IGNORECASE)
_EXPLANATORY_RE = re.compile(r"(?:이다|있다|한다|된다|저장된다|설명|구조)")
_TABLE_METADATA_RE = re.compile(r"(?:자료형\s+길이\(바이트\)\s+설명|\|\s*길이\(바이트\)\s*\|\s*설명)")
_DOCUMENT_PATH_STOPWORDS = {
    "projecthub", "jarvis", "document", "docs", "file", "files", "source", "code",
    "문서", "파일", "코드", "설명", "구조",
}


@dataclass
class RetrievalInputs:
    query: str
    analysis: QueryAnalysis | None
    fragments: list[TypedQueryFragment]
    fts_hits: list[SearchHit]
    vector_hits: list[VectorHit]
    db: object | None
    targeted_file_search: callable
    explicit_file_scoped_query: callable


class RetrievalStrategy(Protocol):
    def augment_candidates(self, inputs: RetrievalInputs) -> tuple[list[SearchHit], list[VectorHit]]: ...
    def protect_post_rerank(
        self,
        *,
        analysis: QueryAnalysis | None,
        query: str,
        hybrid_results: list[HybridSearchResult],
        pre_rerank_results: list[HybridSearchResult],
        chunk_texts: dict[str, str],
    ) -> list[HybridSearchResult]: ...


class DocumentStrategy:
    def augment_candidates(self, inputs: RetrievalInputs) -> tuple[list[SearchHit], list[VectorHit]]:
        fts_hits = list(inputs.fts_hits)
        vector_hits = list(inputs.vector_hits)
        db = inputs.db
        targeted_hits = inputs.targeted_file_search(inputs.query, inputs.fragments)
        if targeted_hits:
            targeted_chunk_ids = {t.chunk_id for t in targeted_hits}
            targeted_doc_ids = {t.document_id for t in targeted_hits}
            if inputs.explicit_file_scoped_query(inputs.query):
                fts_hits = targeted_hits + [
                    h for h in fts_hits
                    if h.chunk_id not in targeted_chunk_ids and h.document_id in targeted_doc_ids
                ]
                vector_hits = [h for h in vector_hits if h.document_id in targeted_doc_ids]
            else:
                fts_hits = targeted_hits + [h for h in fts_hits if h.chunk_id not in targeted_chunk_ids]

        if db is not None:
            path_terms = _resolve_document_path_terms(inputs.analysis)
            if path_terms:
                matched_docs = _find_document_path_matches(db=db, path_terms=path_terms)
                fts_hits = _prepend_document_path_hits(
                    db=db,
                    path_terms=path_terms,
                    existing_hits=fts_hits,
                    matched_docs=matched_docs,
                )
                if matched_docs and len(matched_docs) <= 3:
                    matched_doc_ids = set(matched_docs)
                    vector_hits = [
                        hit for hit in vector_hits
                        if hit.document_id in matched_doc_ids
                    ]
            topic_terms = _resolve_topic_terms(inputs.analysis)
            if topic_terms:
                scoped_doc_ids = None
                if targeted_hits and inputs.explicit_file_scoped_query(inputs.query):
                    scoped_doc_ids = {hit.document_id for hit in targeted_hits}
                fts_hits = _prepend_document_section_hits(
                    db=db,
                    topic_terms=topic_terms,
                    existing_hits=fts_hits,
                    scoped_doc_ids=scoped_doc_ids,
                    negative_terms=_resolve_negative_terms(inputs.analysis),
                )
        return fts_hits, vector_hits

    def protect_post_rerank(
        self,
        *,
        analysis: QueryAnalysis | None,
        query: str,
        hybrid_results: list[HybridSearchResult],
        pre_rerank_results: list[HybridSearchResult],
        chunk_texts: dict[str, str],
    ) -> list[HybridSearchResult]:
        del analysis, query, pre_rerank_results, chunk_texts
        return hybrid_results


class CodeStrategy(DocumentStrategy):
    pass


class TableStrategy:
    def augment_candidates(self, inputs: RetrievalInputs) -> tuple[list[SearchHit], list[VectorHit]]:
        fts_hits = list(inputs.fts_hits)
        vector_hits = list(inputs.vector_hits)
        db = inputs.db
        if db is None:
            return fts_hits, vector_hits

        analysis = inputs.analysis
        row_ids = _resolve_row_ids(inputs.query, analysis)
        fields = _resolve_table_fields(analysis)
        if not row_ids:
            return fts_hits, vector_hits

        existing_ids = {h.chunk_id for h in fts_hits} | {h.chunk_id for h in vector_hits}
        supplemental_hits: list[SearchHit] = []
        for rid in row_ids:
            rows = db.execute(
                "SELECT chunk_id, document_id, text FROM chunks"
                " WHERE heading_path LIKE 'table-row-%'"
                " AND text LIKE ?",
                (f"%Day={rid} |%",),
            ).fetchall()
            for chunk_id, doc_id, text in rows:
                if chunk_id not in existing_ids:
                    supplemental_hits.append(SearchHit(
                        chunk_id=chunk_id,
                        document_id=doc_id,
                        score=50.0,
                        snippet=text[:200],
                    ))
                    existing_ids.add(chunk_id)
        if supplemental_hits:
            fts_hits = supplemental_hits + [h for h in fts_hits if h.chunk_id not in existing_ids]

        if not fields:
            return fts_hits, vector_hits

        existing_ids = {h.chunk_id for h in fts_hits} | {h.chunk_id for h in vector_hits}
        table_hits: list[SearchHit] = []
        for rid in row_ids:
            for field in fields:
                rows = db.execute(
                    "SELECT chunk_id, document_id, text FROM chunks"
                    " WHERE heading_path LIKE 'table-row-%'"
                    " AND text LIKE ?"
                    " AND text LIKE ?",
                    (f"%Day={rid} |%", f"%{field}=%"),
                ).fetchall()
                for chunk_id, doc_id, text in rows:
                    if chunk_id not in existing_ids:
                        table_hits.append(SearchHit(
                            chunk_id=chunk_id,
                            document_id=doc_id,
                            score=100.0,
                            snippet=text[:200],
                        ))
                        existing_ids.add(chunk_id)
        if table_hits:
            fts_hits = table_hits + [h for h in fts_hits if h.chunk_id not in existing_ids]
        return fts_hits, vector_hits

    def protect_post_rerank(
        self,
        *,
        analysis: QueryAnalysis | None,
        query: str,
        hybrid_results: list[HybridSearchResult],
        pre_rerank_results: list[HybridSearchResult],
        chunk_texts: dict[str, str],
    ) -> list[HybridSearchResult]:
        row_ids = _resolve_row_ids(query, analysis)
        if not row_ids:
            return hybrid_results
        reranked_ids = {r.chunk_id for r in hybrid_results}
        for result in pre_rerank_results:
            if result.chunk_id in reranked_ids:
                continue
            chunk_text = chunk_texts.get(result.chunk_id, "")
            for row_id in row_ids:
                if f"Day={row_id} " in chunk_text or f"Day={row_id}|" in chunk_text:
                    hybrid_results.append(result)
                    reranked_ids.add(result.chunk_id)
                    break
        return hybrid_results


def select_retrieval_strategy(analysis: QueryAnalysis | None) -> RetrievalStrategy:
    task = analysis.retrieval_task if analysis is not None else "document_qa"
    if task == "table_lookup":
        return TableStrategy()
    if task == "code_lookup":
        return CodeStrategy()
    return DocumentStrategy()


def _resolve_row_ids(query: str, analysis: QueryAnalysis | None) -> list[str]:
    if analysis is not None:
        raw_values = analysis.entities.get("row_ids")
        if isinstance(raw_values, list):
            values = [str(value) for value in raw_values if str(value).strip()]
            if values:
                return values
    return list(dict.fromkeys(_ROW_ID_RE.findall(query)))


def _resolve_table_fields(analysis: QueryAnalysis | None) -> list[str]:
    if analysis is None:
        return []
    raw_values = analysis.entities.get("fields")
    if isinstance(raw_values, list):
        return [str(value) for value in raw_values if str(value).strip()]
    return []


def _resolve_topic_terms(analysis: QueryAnalysis | None) -> list[str]:
    if analysis is None:
        return []
    raw_values = analysis.entities.get("topic_terms")
    if isinstance(raw_values, list):
        return [str(value) for value in raw_values if len(str(value).strip()) >= 2]
    return []


def _resolve_negative_terms(analysis: QueryAnalysis | None) -> list[str]:
    if analysis is None:
        return []
    raw_values = analysis.entities.get("negative_terms")
    if isinstance(raw_values, list):
        return [str(value) for value in raw_values if len(str(value).strip()) >= 2]
    return []


def _resolve_document_path_terms(analysis: QueryAnalysis | None) -> list[str]:
    if analysis is None:
        return []
    terms: list[str] = []
    seen: set[str] = set()
    for raw_term in analysis.search_terms:
        for term in _expand_document_path_terms(str(raw_term).strip()):
            normalized = _normalize_match_text(term)
            if len(normalized) < 4:
                continue
            if normalized in _DOCUMENT_PATH_STOPWORDS:
                continue
            if normalized in seen:
                continue
            seen.add(normalized)
            terms.append(term)
    return terms


def _expand_document_path_terms(term: str) -> list[str]:
    if not term:
        return []

    expanded: list[str] = []
    seen: set[str] = set()
    candidates = [term]
    stripped = _strip_topic_suffix(term)
    if stripped != term:
        candidates.append(stripped)

    for candidate in candidates:
        lowered = candidate.casefold()
        if lowered not in seen:
            expanded.append(candidate)
            seen.add(lowered)
        for alias in _BILINGUAL_EXPANSIONS.get(candidate, ()):
            alias_lowered = alias.casefold()
            if alias_lowered in seen:
                continue
            expanded.append(alias)
            seen.add(alias_lowered)
    return expanded


def _prepend_document_section_hits(
    *,
    db: object,
    topic_terms: list[str],
    existing_hits: list[SearchHit],
    scoped_doc_ids: set[str] | None = None,
    negative_terms: list[str] | None = None,
) -> list[SearchHit]:
    if not topic_terms:
        return existing_hits

    existing_ids = {hit.chunk_id for hit in existing_hits}
    rows = db.execute(
        "SELECT chunk_id, document_id, text, heading_path FROM chunks"
        " WHERE heading_path NOT LIKE 'table-row-%'"
        " AND heading_path NOT LIKE 'table-summary-%'"
    ).fetchall()

    supplemental: list[SearchHit] = []
    for chunk_id, document_id, text, heading_path in rows:
        if chunk_id in existing_ids:
            continue
        if scoped_doc_ids is not None and document_id not in scoped_doc_ids:
            continue
        normalized_text = text or ""
        normalized_heading = heading_path or ""
        normalized_text_cmp = _normalize_match_text(normalized_text)
        normalized_heading_cmp = _normalize_match_text(normalized_heading)
        combined = f"{normalized_heading_cmp} {normalized_text_cmp}"

        heading_matches = sum(1 for term in topic_terms if _normalize_match_text(term) in normalized_heading_cmp)
        text_matches = sum(1 for term in topic_terms if _normalize_match_text(term) in combined)
        if heading_matches == 0 and text_matches < 2:
            continue

        score = (heading_matches * 20.0) + (text_matches * 4.0)
        phrase_matches = sum(
            1 for term in topic_terms if " " in term and _normalize_match_text(term) in combined
        )
        score += phrase_matches * 12.0
        if _EXPLANATORY_RE.search(normalized_text):
            score += 6.0
        if heading_path.lower().startswith("table-"):
            score -= 10.0
        if _TABLE_METADATA_RE.search(normalized_text) and not _EXPLANATORY_RE.search(normalized_text):
            score -= 10.0
        if negative_terms:
            neg_matches = sum(
                1 for term in negative_terms if _normalize_match_text(term) in combined
            )
            score -= neg_matches * 20.0
        if score < 12.0:
            continue

        supplemental.append(SearchHit(
            chunk_id=chunk_id,
            document_id=document_id,
            score=score,
            snippet=(normalized_text or normalized_heading)[:200],
        ))
        existing_ids.add(chunk_id)

    if not supplemental:
        return existing_hits

    supplemental.sort(key=lambda hit: hit.score, reverse=True)
    return supplemental + [hit for hit in existing_hits if hit.chunk_id not in {item.chunk_id for item in supplemental}]


def _prepend_document_path_hits(
    *,
    db: object,
    path_terms: list[str],
    existing_hits: list[SearchHit],
    matched_docs: dict[str, str] | None = None,
) -> list[SearchHit]:
    if not path_terms:
        return existing_hits

    existing_ids = {hit.chunk_id for hit in existing_hits}
    supplemental: list[SearchHit] = []
    try:
        effective_matches = matched_docs if matched_docs is not None else _find_document_path_matches(
            db=db,
            path_terms=path_terms,
        )
        if not effective_matches:
            return existing_hits

        for term in path_terms:
            variants = _path_term_variants(term)
            term_matches = {
                document_id: path
                for document_id, path in effective_matches.items()
                if any(variant in path.casefold() for variant in variants)
            }
            if not term_matches or len(term_matches) > 3:
                continue

            for document_id, path in term_matches.items():
                chunk_rows = db.execute(
                    "SELECT chunk_id, document_id, text FROM chunks WHERE document_id = ?",
                    (document_id,),
                ).fetchall()
                normalized_path = path.casefold()
                exact_name_match = any(variant in normalized_path for variant in variants)
                for chunk_id, doc_id, text in chunk_rows:
                    if chunk_id in existing_ids:
                        continue
                    score = 46.0 + min(len(term), 12)
                    if exact_name_match:
                        score += 8.0
                    supplemental.append(SearchHit(
                        chunk_id=chunk_id,
                        document_id=doc_id,
                        score=score,
                        snippet=(text or "")[:200],
                    ))
                    existing_ids.add(chunk_id)
    except Exception:
        return existing_hits

    if not supplemental:
        return existing_hits
    supplemental.sort(key=lambda hit: hit.score, reverse=True)
    return supplemental + [hit for hit in existing_hits if hit.chunk_id not in {item.chunk_id for item in supplemental}]


def _normalize_match_text(value: str) -> str:
    return unicodedata.normalize("NFC", value).casefold().replace(" ", "")


def _path_term_variants(term: str) -> set[str]:
    return {
        term.casefold(),
        term.replace(" ", "_").casefold(),
        term.replace(" ", "-").casefold(),
    }


def _find_document_path_matches(*, db: object, path_terms: list[str]) -> dict[str, str]:
    matched_docs: dict[str, str] = {}
    for term in path_terms:
        for variant in _path_term_variants(term):
            rows = db.execute(
                "SELECT document_id, path FROM documents"
                " WHERE indexing_status = 'INDEXED'"
                " AND LOWER(path) LIKE ?",
                (f"%{variant}%",),
            ).fetchall()
            for document_id, path in rows:
                matched_docs[str(document_id)] = str(path)
    if len(matched_docs) > 3:
        return {}
    return matched_docs
