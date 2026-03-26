from __future__ import annotations

import sqlite3

from jarvis.contracts import SearchHit
from jarvis.contracts import HybridSearchResult
from jarvis.core.planner import QueryAnalysis
from jarvis.retrieval.strategy import (
    DocumentStrategy,
    RetrievalInputs,
    TableStrategy,
    select_retrieval_strategy,
)


def test_selects_document_strategy_for_document_qa() -> None:
    strategy = select_retrieval_strategy(QueryAnalysis(retrieval_task="document_qa"))
    assert isinstance(strategy, DocumentStrategy)


def test_selects_table_strategy_for_table_lookup() -> None:
    strategy = select_retrieval_strategy(QueryAnalysis(retrieval_task="table_lookup"))
    assert isinstance(strategy, TableStrategy)


def test_table_strategy_preserves_row_hits_after_rerank() -> None:
    strategy = TableStrategy()
    analysis = QueryAnalysis(retrieval_task="table_lookup", entities={"row_ids": ["11"]})
    pre_rerank = [
        HybridSearchResult(
            chunk_id="chunk-11",
            document_id="doc-diet",
            rrf_score=0.5,
            snippet="",
        )
    ]
    reranked = []
    chunk_texts = {"chunk-11": "Day=11 | Breakfast=구운계란2+아몬드 | Dinner=두부+아보카도"}

    protected = strategy.protect_post_rerank(
        analysis=analysis,
        query="식단표에서 11번 메뉴 알려줘",
        hybrid_results=reranked,
        pre_rerank_results=pre_rerank,
        chunk_texts=chunk_texts,
    )

    assert [item.chunk_id for item in protected] == ["chunk-11"]


def test_document_strategy_does_not_inject_table_row_logic() -> None:
    strategy = DocumentStrategy()
    analysis = QueryAnalysis(retrieval_task="document_qa")
    fts_hits, vector_hits = strategy.augment_candidates(
        RetrievalInputs(
            query="한글문서 파일형식에서 11번 그리기 개체 자료 구조 기본 구조 설명",
            analysis=analysis,
            fragments=[],
            fts_hits=[],
            vector_hits=[],
            db=None,
            targeted_file_search=lambda query, fragments: [],
            explicit_file_scoped_query=lambda query: False,
        )
    )

    assert fts_hits == []
    assert vector_hits == []


def test_document_strategy_prepends_section_aware_hits() -> None:
    db = sqlite3.connect(":memory:")
    db.execute(
        "CREATE TABLE chunks (chunk_id TEXT PRIMARY KEY, document_id TEXT, text TEXT, heading_path TEXT, line_start INTEGER, line_end INTEGER)"
    )
    db.execute(
        "INSERT INTO chunks VALUES (?, ?, ?, ?, ?, ?)",
        (
            "chunk-body",
            "doc-hwp",
            "그리기 개체는 여러 개의 개체를 하나의 틀로 묶을 수 있기 때문에 파일상에는 다음과 같은 구조로 저장된다.",
            "문서 구조 > 그리기 개체 자료 구조 > 기본 구조",
            0,
            0,
        ),
    )
    db.execute(
        "INSERT INTO chunks VALUES (?, ?, ?, ?, ?, ?)",
        (
            "chunk-table",
            "doc-diet",
            "Day=11 | Breakfast=구운계란2+아몬드",
            "table-row-Diet-10",
            1,
            1,
        ),
    )
    db.commit()

    strategy = DocumentStrategy()
    analysis = QueryAnalysis(
        retrieval_task="document_qa",
        entities={"topic_terms": ["그리기", "개체", "기본", "구조"]},
    )
    fts_hits, _ = strategy.augment_candidates(
        RetrievalInputs(
            query="한글문서 파일형식에서 그리기 개체 자료 구조 기본 구조 설명",
            analysis=analysis,
            fragments=[],
            fts_hits=[SearchHit(chunk_id="fallback", document_id="doc-other", score=1.0, snippet="fallback")],
            vector_hits=[],
            db=db,
            targeted_file_search=lambda query, fragments: [],
            explicit_file_scoped_query=lambda query: False,
        )
    )

    assert fts_hits[0].chunk_id == "chunk-body"
    assert all(hit.chunk_id != "chunk-table" for hit in fts_hits)


def test_document_strategy_penalizes_negated_topic_hits() -> None:
    db = sqlite3.connect(":memory:")
    db.execute(
        "CREATE TABLE chunks (chunk_id TEXT PRIMARY KEY, document_id TEXT, text TEXT, heading_path TEXT, line_start INTEGER, line_end INTEGER)"
    )
    db.execute(
        "INSERT INTO chunks VALUES (?, ?, ?, ?, ?, ?)",
        (
            "chunk-negated",
            "doc-hwp",
            "하이퍼 텍스트 정보가 포함되어 있다.",
            "",
            0,
            0,
        ),
    )
    db.execute(
        "INSERT INTO chunks VALUES (?, ?, ?, ?, ?, ?)",
        (
            "chunk-target",
            "doc-hwp",
            "그리기 개체 자료 구조 기본 구조 그리기 개체는 여러 개의 개체를 하나의 틀로 묶을 수 있기 때문에 파일상에는 다음과 같은 구조로 저장된다.",
            "",
            1,
            1,
        ),
    )
    db.commit()

    strategy = DocumentStrategy()
    analysis = QueryAnalysis(
        retrieval_task="document_qa",
        entities={
            "topic_terms": ["그리기 개체", "자료 구조", "기본 구조"],
            "negative_terms": ["하이퍼 텍스트 정보"],
        },
    )
    fts_hits, _ = strategy.augment_candidates(
        RetrievalInputs(
            query="하이퍼 텍스트 정보가 아니라 기본 구조 설명",
            analysis=analysis,
            fragments=[],
            fts_hits=[],
            vector_hits=[],
            db=db,
            targeted_file_search=lambda query, fragments: [],
            explicit_file_scoped_query=lambda query: False,
        )
    )

    assert fts_hits[0].chunk_id == "chunk-target"
