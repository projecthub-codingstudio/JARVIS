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


def test_table_strategy_prepends_structured_table_summary_for_overview_query() -> None:
    db = sqlite3.connect(":memory:")
    db.execute(
        "CREATE TABLE documents (document_id TEXT PRIMARY KEY, path TEXT, indexing_status TEXT)"
    )
    db.execute(
        "CREATE TABLE chunks (chunk_id TEXT PRIMARY KEY, document_id TEXT, text TEXT, heading_path TEXT, line_start INTEGER, line_end INTEGER)"
    )
    db.execute(
        "INSERT INTO documents VALUES (?, ?, ?)",
        ("doc-diet", "/tmp/14day_diet_supplements_final.xlsx", "INDEXED"),
    )
    db.execute(
        "INSERT INTO documents VALUES (?, ?, ?)",
        ("doc-hwp", "/tmp/한글문서파일형식_revision1.1_20110124.hwp", "INDEXED"),
    )
    db.execute(
        "INSERT INTO chunks VALUES (?, ?, ?, ?, ?, ?)",
        (
            "chunk-diet-summary",
            "doc-diet",
            "[Diet+Supplements_14days] Table with 14 rows. Columns: Day, Breakfast, Lunch, Dinner",
            "table-summary-Diet+Supplements_14days",
            0,
            0,
        ),
    )
    db.execute(
        "INSERT INTO chunks VALUES (?, ?, ?, ?, ?, ?)",
        (
            "chunk-diet-row",
            "doc-diet",
            "Day=1 | Breakfast=구운계란2+방울토마토 | Lunch=닭가슴살+현미밥1/2 | Dinner=두부스테이크",
            "table-row-Diet+Supplements_14days-0",
            1,
            1,
        ),
    )
    db.execute(
        "INSERT INTO chunks VALUES (?, ?, ?, ?, ?, ?)",
        (
            "chunk-hwp-table",
            "doc-hwp",
            "[표 대각선 종류] 값 | 설명 [표 대각선 종류] 0 | Slash",
            "table-full-표 대각선 종류",
            2,
            2,
        ),
    )
    db.commit()

    strategy = TableStrategy()
    analysis = QueryAnalysis(
        retrieval_task="table_lookup",
        search_terms=["다이어트", "식단표", "diet", "menu"],
    )
    fts_hits, _ = strategy.augment_candidates(
        RetrievalInputs(
            query="다이어트 식단표 보여줘",
            analysis=analysis,
            fragments=[],
            fts_hits=[SearchHit(chunk_id="chunk-hwp-table", document_id="doc-hwp", score=3.0, snippet="generic table")],
            vector_hits=[],
            db=db,
            targeted_file_search=lambda query, fragments: [],
            explicit_file_scoped_query=lambda query: False,
        )
    )

    assert fts_hits[0].chunk_id == "chunk-diet-summary"
    assert any(hit.chunk_id == "chunk-diet-row" for hit in fts_hits[:3])


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


def test_document_strategy_prepends_document_path_hits_for_brochure_terms() -> None:
    db = sqlite3.connect(":memory:")
    db.execute(
        "CREATE TABLE documents (document_id TEXT PRIMARY KEY, path TEXT, indexing_status TEXT)"
    )
    db.execute(
        "CREATE TABLE chunks (chunk_id TEXT PRIMARY KEY, document_id TEXT, text TEXT, heading_path TEXT, line_start INTEGER, line_end INTEGER)"
    )
    db.execute(
        "INSERT INTO documents VALUES (?, ?, ?)",
        ("doc-brochure", "/tmp/ProjectHub_Brochure.pptx", "INDEXED"),
    )
    db.execute(
        "INSERT INTO documents VALUES (?, ?, ?)",
        ("doc-other", "/tmp/pipeline.py", "INDEXED"),
    )
    db.execute(
        "INSERT INTO chunks VALUES (?, ?, ?, ?, ?, ?)",
        ("chunk-brochure", "doc-brochure", "ProjectHub macOS용 올인원 프로젝트 관리 도구", "", 0, 0),
    )
    db.execute(
        "INSERT INTO chunks VALUES (?, ?, ?, ?, ?, ?)",
        ("chunk-other", "doc-other", "class Pipeline: pass", "code:python", 1, 1),
    )
    db.commit()

    strategy = DocumentStrategy()
    analysis = QueryAnalysis(
        retrieval_task="document_qa",
        search_terms=["projecthub", "brochure"],
    )
    fts_hits, _ = strategy.augment_candidates(
        RetrievalInputs(
            query="ProjectHub 브로셔에서 ProjectHub를 어떻게 소개하나요?",
            analysis=analysis,
            fragments=[],
            fts_hits=[SearchHit(chunk_id="chunk-other", document_id="doc-other", score=2.0, snippet="class Pipeline: pass")],
            vector_hits=[],
            db=db,
            targeted_file_search=lambda query, fragments: [],
            explicit_file_scoped_query=lambda query: False,
        )
    )

    assert fts_hits[0].chunk_id == "chunk-brochure"


def test_document_strategy_normalizes_korean_brochure_path_terms() -> None:
    db = sqlite3.connect(":memory:")
    db.execute(
        "CREATE TABLE documents (document_id TEXT PRIMARY KEY, path TEXT, indexing_status TEXT)"
    )
    db.execute(
        "CREATE TABLE chunks (chunk_id TEXT PRIMARY KEY, document_id TEXT, text TEXT, heading_path TEXT, line_start INTEGER, line_end INTEGER)"
    )
    db.execute(
        "INSERT INTO documents VALUES (?, ?, ?)",
        ("doc-brochure", "/tmp/ProjectHub_Brochure.pptx", "INDEXED"),
    )
    db.execute(
        "INSERT INTO chunks VALUES (?, ?, ?, ?, ?, ?)",
        ("chunk-brochure", "doc-brochure", "ProjectHub macOS용 올인원 프로젝트 관리 도구", "", 0, 0),
    )
    db.commit()

    strategy = DocumentStrategy()
    analysis = QueryAnalysis(
        retrieval_task="document_qa",
        search_terms=["projecthub", "브로셔에서", "projecthub를", "어떻게", "소개하나요", "브로셔"],
    )
    fts_hits, _ = strategy.augment_candidates(
        RetrievalInputs(
            query="ProjectHub 브로셔에서 ProjectHub를 어떻게 소개하나요?",
            analysis=analysis,
            fragments=[],
            fts_hits=[],
            vector_hits=[],
            db=db,
            targeted_file_search=lambda query, fragments: [],
            explicit_file_scoped_query=lambda query: False,
        )
    )

    assert fts_hits[0].chunk_id == "chunk-brochure"


def test_document_strategy_prefers_content_matching_chunk_within_path_matched_document() -> None:
    db = sqlite3.connect(":memory:")
    db.execute(
        "CREATE TABLE documents (document_id TEXT PRIMARY KEY, path TEXT, indexing_status TEXT)"
    )
    db.execute(
        "CREATE TABLE chunks (chunk_id TEXT PRIMARY KEY, document_id TEXT, text TEXT, heading_path TEXT, line_start INTEGER, line_end INTEGER)"
    )
    db.execute(
        "INSERT INTO documents VALUES (?, ?, ?)",
        ("doc-brochure", "/tmp/ProjectHub_Brochure.pptx", "INDEXED"),
    )
    db.execute(
        "INSERT INTO chunks VALUES (?, ?, ?, ?, ?, ?)",
        (
            "chunk-intro",
            "doc-brochure",
            "[Slide 1] ProjectHub macOS용 올인원 프로젝트 관리 도구",
            "",
            0,
            0,
        ),
    )
    db.execute(
        "INSERT INTO chunks VALUES (?, ?, ?, ?, ?, ?)",
        (
            "chunk-features",
            "doc-brochure",
            "[Slide 5] FEATURES 개발자를 위한 모든 기능 코드 다이어그램 파일 브라우저 Git 통합 개발자 도구",
            "",
            1,
            1,
        ),
    )
    db.commit()

    strategy = DocumentStrategy()
    analysis = QueryAnalysis(
        retrieval_task="document_qa",
        search_terms=["projecthub_brochure", "개발자를", "위한", "기능에는"],
    )
    fts_hits, _ = strategy.augment_candidates(
        RetrievalInputs(
            query="projecthub_brochure 에서 개발자를 위한 기능에는 어떤 것이 있나요 ?",
            analysis=analysis,
            fragments=[],
            fts_hits=[],
            vector_hits=[],
            db=db,
            targeted_file_search=lambda query, fragments: [],
            explicit_file_scoped_query=lambda query: False,
        )
    )

    assert fts_hits[0].chunk_id == "chunk-features"


def test_document_strategy_reorders_existing_path_matched_chunks_by_content() -> None:
    db = sqlite3.connect(":memory:")
    db.execute(
        "CREATE TABLE documents (document_id TEXT PRIMARY KEY, path TEXT, indexing_status TEXT)"
    )
    db.execute(
        "CREATE TABLE chunks (chunk_id TEXT PRIMARY KEY, document_id TEXT, text TEXT, heading_path TEXT, line_start INTEGER, line_end INTEGER)"
    )
    db.execute(
        "INSERT INTO documents VALUES (?, ?, ?)",
        ("doc-brochure", "/tmp/ProjectHub_Brochure.pptx", "INDEXED"),
    )
    db.execute(
        "INSERT INTO chunks VALUES (?, ?, ?, ?, ?, ?)",
        (
            "chunk-intro",
            "doc-brochure",
            "[Slide 1] ProjectHub macOS용 올인원 프로젝트 관리 도구",
            "",
            0,
            0,
        ),
    )
    db.execute(
        "INSERT INTO chunks VALUES (?, ?, ?, ?, ?, ?)",
        (
            "chunk-features",
            "doc-brochure",
            "[Slide 5] FEATURES 개발자를 위한 모든 기능 코드 다이어그램 파일 브라우저 Git 통합 개발자 도구",
            "",
            1,
            1,
        ),
    )
    db.commit()

    strategy = DocumentStrategy()
    analysis = QueryAnalysis(
        retrieval_task="document_qa",
        search_terms=["projecthub_brochure", "개발자를", "위한", "기능에는"],
    )
    fts_hits, _ = strategy.augment_candidates(
        RetrievalInputs(
            query="projecthub_brochure 에서 개발자를 위한 기능에는 어떤 것이 있나요 ?",
            analysis=analysis,
            fragments=[],
            fts_hits=[SearchHit(chunk_id="chunk-intro", document_id="doc-brochure", score=2.0, snippet="intro")],
            vector_hits=[],
            db=db,
            targeted_file_search=lambda query, fragments: [],
            explicit_file_scoped_query=lambda query: False,
        )
    )

    assert fts_hits[0].chunk_id == "chunk-features"
