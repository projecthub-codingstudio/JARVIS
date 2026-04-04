"""Tests for stub response rendering in MLX runtime."""

from __future__ import annotations

from jarvis.contracts import CitationRecord, CitationState, EvidenceItem, TypedQueryFragment, VerifiedEvidenceSet
from jarvis.runtime.mlx_runtime import _build_stub_grounded_response, build_stub_spoken_response


def _table_evidence() -> VerifiedEvidenceSet:
    items = (
        EvidenceItem(
            chunk_id="chunk-day-2",
            document_id="doc-1",
            text="[Diet+Supplements_14days] Day=2 | Breakfast=계란후라이2+오이 | Lunch=닭가슴살+샐러드+아보카도1/4 | Dinner=두부부침+피망볶음 | Drinks=녹차",
            citation=CitationRecord(document_id="doc-1", chunk_id="chunk-day-2", label="[1]", state=CitationState.VALID),
            relevance_score=0.9,
            source_path="/tmp/14day_diet_supplements_final.xlsx",
            heading_path="table-row-Diet+Supplements_14days-1",
        ),
        EvidenceItem(
            chunk_id="chunk-day-3",
            document_id="doc-1",
            text="[Diet+Supplements_14days] Day=3 | Breakfast=구운계란2+요거트+베리 | Lunch=닭가슴살+현미밥1/3+김2장 | Dinner=순두부+방울토마토 | Drinks=레몬물",
            citation=CitationRecord(document_id="doc-1", chunk_id="chunk-day-3", label="[2]", state=CitationState.VALID),
            relevance_score=0.8,
            source_path="/tmp/14day_diet_supplements_final.xlsx",
            heading_path="table-row-Diet+Supplements_14days-2",
        ),
    )
    return VerifiedEvidenceSet(
        items=items,
        query_fragments=(TypedQueryFragment(text="식단표 2일차 3일차 메뉴", language="ko", query_type="keyword"),),
    )


def test_stub_response_formats_table_menu_readably() -> None:
    response = _build_stub_grounded_response("식단표에서 2일차 3일차 메뉴 알려줘", _table_evidence())

    assert "2일차 메뉴는" in response
    assert "3일차 메뉴는" in response
    assert "점심은 닭가슴살+현미밥1/3+김2장" in response


def test_stub_response_formats_specific_meal_readably() -> None:
    response = _build_stub_grounded_response("식단표에서 3일차 점심을 알려줘", _table_evidence())

    assert "3일차 점심은 닭가슴살+현미밥1/3+김2장입니다." in response
    assert "확인된 근거는" not in response
    assert "근거:" not in response


def test_stub_spoken_response_naturalizes_table_values() -> None:
    response = build_stub_spoken_response("식단표에서 3일차 점심을 알려줘", _table_evidence())

    assert response == "3일차 점심은 닭가슴살과 현미밥 삼 분의 일과 김 두 장입니다."


def test_stub_response_formats_multiple_requested_meals() -> None:
    response = _build_stub_grounded_response("다이어트 식단에서 2일차 3일차 아침 저녁 메뉴 알려줘", _table_evidence())

    assert "2일차 메뉴는 아침은 계란후라이2+오이, 저녁은 두부부침+피망볶음입니다." in response
    assert "3일차 메뉴는 아침은 구운계란2+요거트+베리, 저녁은 순두부+방울토마토입니다." in response


def test_stub_response_formats_sql_table_columns_for_schema_query() -> None:
    evidence = VerifiedEvidenceSet(
        items=(
            EvidenceItem(
                chunk_id="chunk-sql-columns",
                document_id="doc-sql",
                text=(
                    "[SQL Tables: tbl_day_chart]\n\n"
                    "[Table: tbl_day_chart (일봉 차트 데이타)]\n"
                    "  column | type | nullable | description\n"
                    "  ------------------------------------------------------------\n"
                    "  code | varchar(7) | NOT NULL | 코드\n"
                    "  service_date | varchar(8) | NOT NULL | 날짜\n"
                    "  시가 | int | NULL | 시가\n"
                    "  종가 | int | NULL | 종가\n"
                ),
                citation=CitationRecord(document_id="doc-sql", chunk_id="chunk-sql-columns", label="[1]", state=CitationState.VALID),
                relevance_score=0.91,
                source_path="/tmp/tbl_day_chart.sql",
                heading_path="",
            ),
        ),
        query_fragments=(TypedQueryFragment(text="day_chart 컬럼 정보", language="ko", query_type="keyword"),),
    )

    response = _build_stub_grounded_response(
        "day_chart 테이블의 컬럼 정보 보여줘.",
        evidence,
    )

    assert "`tbl_day_chart` 테이블의 컬럼 정보입니다." in response
    assert "`code`: `varchar(7)`, `NOT NULL`, 설명 `코드`" in response
    assert "`service_date`: `varchar(8)`, `NOT NULL`, 설명 `날짜`" in response
    assert "[Table: tbl_day_chart" not in response


def test_stub_response_filters_sql_table_column_when_specific_column_requested() -> None:
    evidence = VerifiedEvidenceSet(
        items=(
            EvidenceItem(
                chunk_id="chunk-sql-columns",
                document_id="doc-sql",
                text=(
                    "[SQL Tables: tbl_day_chart]\n\n"
                    "[Table: tbl_day_chart (일봉 차트 데이타)]\n"
                    "  column | type | nullable | description\n"
                    "  ------------------------------------------------------------\n"
                    "  code | varchar(7) | NOT NULL | 코드\n"
                    "  service_date | varchar(8) | NOT NULL | 날짜\n"
                    "  시가 | int | NULL | 시가\n"
                    "  종가 | int | NULL | 종가\n"
                ),
                citation=CitationRecord(document_id="doc-sql", chunk_id="chunk-sql-columns", label="[1]", state=CitationState.VALID),
                relevance_score=0.91,
                source_path="/tmp/tbl_day_chart.sql",
                heading_path="",
            ),
        ),
        query_fragments=(TypedQueryFragment(text="day_chart service_date 컬럼 정보", language="ko", query_type="keyword"),),
    )

    response = _build_stub_grounded_response(
        "day_chart 테이블의 service_date 컬럼 정보 보여줘.",
        evidence,
    )

    assert "`service_date`: `varchar(8)`, `NOT NULL`, 설명 `날짜`" in response
    assert "`code`: `varchar(7)`" not in response


def test_stub_document_response_prefers_query_matching_excerpt() -> None:
    evidence = VerifiedEvidenceSet(
        items=(
            EvidenceItem(
                chunk_id="chunk-doc-1",
                document_id="doc-hwp",
                text=(
                    "[HWP Table 456] 오프셋 자료형 의미 설명 0 hchar 특수 문자 코드 늘 31이다. "
                    "2 hchar 특수 문자 코드 늘 31이다. 전체 길이 4. "
                    "그리기 개체 자료 구조 기본 구조 그리기 개체는 여러 개의 개체를 하나의 틀로 묶을 수 있기 때문에, "
                    "하나의 그림 코드에 하나 이상의 개체가 존재할 수 있다. 파일상에는 다음과 같은 구조로 저장된다. 그림 정보 348 바이트."
                ),
                citation=CitationRecord(document_id="doc-hwp", chunk_id="chunk-doc-1", label="[1]", state=CitationState.VALID),
                relevance_score=0.91,
                source_path="/tmp/hwp-format.hwp",
                heading_path="section-1",
            ),
        ),
        query_fragments=(TypedQueryFragment(text="그리기의 개체 자료 구조 중 기본 구조", language="ko", query_type="keyword"),),
    )

    response = _build_stub_grounded_response(
        "한글 문서 형식에서 그리기의 개체 자료 구조 중 기본 구조에 대해 설명해 주세요",
        evidence,
    )

    assert "그리기 개체 자료 구조 기본 구조" in response
    assert "하나의 그림 코드에 하나 이상의 개체가 존재할 수 있다" in response
    assert "현재 모델 생성 경로가 비활성" not in response
    assert "근거:" not in response


def test_stub_document_response_skips_heading_only_excerpt() -> None:
    evidence = VerifiedEvidenceSet(
        items=(
            EvidenceItem(
                chunk_id="chunk-heading",
                document_id="doc-hwp",
                text="그리기 개체 자료 구조",
                citation=CitationRecord(document_id="doc-hwp", chunk_id="chunk-heading", label="[1]", state=CitationState.VALID),
                relevance_score=0.95,
                source_path="/tmp/hwp-format.hwp",
                heading_path="section-heading",
            ),
            EvidenceItem(
                chunk_id="chunk-body",
                document_id="doc-hwp",
                text=(
                    "그리기 개체 자료 구조 기본 구조 그리기 개체는 여러 개의 개체를 하나의 틀로 묶을 수 있기 때문에, "
                    "하나의 그림 코드에 하나 이상의 개체가 존재할 수 있다. 파일상에는 다음과 같은 구조로 저장된다."
                ),
                citation=CitationRecord(document_id="doc-hwp", chunk_id="chunk-body", label="[2]", state=CitationState.VALID),
                relevance_score=0.85,
                source_path="/tmp/hwp-format.hwp",
                heading_path="section-body",
            ),
        ),
        query_fragments=(TypedQueryFragment(text="그리기 개체 자료 구조 기본 구조", language="ko", query_type="keyword"),),
    )

    response = _build_stub_grounded_response(
        "한글 문서 형식에서 그리기 개체 자료 구조 중 기본 구조에 대해 설명해 주세요",
        evidence,
    )

    assert "하나의 그림 코드에 하나 이상의 개체가 존재할 수 있다" in response


def test_stub_document_response_ignores_non_spreadsheet_table_rows() -> None:
    evidence = VerifiedEvidenceSet(
        items=(
            EvidenceItem(
                chunk_id="chunk-doc-1",
                document_id="doc-hwp",
                text=(
                    "그리기 개체 자료 구조 기본 구조 그리기 개체는 여러 개의 개체를 하나의 틀로 묶을 수 있기 때문에, "
                    "하나의 그림 코드에 하나 이상의 개체가 존재할 수 있다. 파일상에는 다음과 같은 구조로 저장된다."
                ),
                citation=CitationRecord(document_id="doc-hwp", chunk_id="chunk-doc-1", label="[1]", state=CitationState.VALID),
                relevance_score=0.95,
                source_path="/tmp/hwp-format.hwp",
                heading_path="section-1",
            ),
            EvidenceItem(
                chunk_id="chunk-sql-1",
                document_id="doc-sql",
                text="[tbl_day_chart] Day=9 | Lunch=wrong-answer",
                citation=CitationRecord(document_id="doc-sql", chunk_id="chunk-sql-1", label="[2]", state=CitationState.VALID),
                relevance_score=0.4,
                source_path="/tmp/tbl_day_chart.sql",
                heading_path="table-row-sql-0",
            ),
        ),
        query_fragments=(TypedQueryFragment(text="그리기 개체 자료 구조 기본 구조", language="ko", query_type="keyword"),),
    )

    response = _build_stub_grounded_response(
        "한글 문서 형식에서 그리기 개체 자료 구조 중 기본 구조에 대해 설명해 주세요",
        evidence,
    )

    assert "그리기 개체 자료 구조 기본 구조" in response
    assert "tbl_day_chart" not in response


def test_stub_document_response_keeps_complete_sentence_boundary() -> None:
    evidence = VerifiedEvidenceSet(
        items=(
            EvidenceItem(
                chunk_id="chunk-doc-2",
                document_id="doc-hwp",
                text=(
                    "그리기 개체 자료 구조 기본 구조 그리기 개체는 여러 개의 개체를 하나의 틀로 묶을 수 있기 때문에, "
                    "하나의 그림 코드에 하나 이상의 개체가 존재할 수 있다. 파일상에는 다음과 같은 구조로 저장된다. "
                    "그림 정보 348 바이트와 틀 헤더 28 바이트가 뒤따른다."
                ),
                citation=CitationRecord(document_id="doc-hwp", chunk_id="chunk-doc-2", label="[1]", state=CitationState.VALID),
                relevance_score=0.95,
                source_path="/tmp/hwp-format.hwp",
                heading_path="그리기 개체 자료 구조 > 기본 구조",
            ),
        ),
        query_fragments=(TypedQueryFragment(text="그리기 개체 자료 구조 기본 구조", language="ko", query_type="keyword"),),
    )

    response = _build_stub_grounded_response(
        "한글 문서 형식에서 그리기 개체 자료 구조 중 기본 구조에 대해 설명해 주세요",
        evidence,
    )

    assert "하나의 그림 코드에 하나 이상의 개체가 존재할 수 있다." in response
    assert "하나 이상의\n" not in response


def test_stub_document_response_prefers_basic_structure_excerpt_over_related_section() -> None:
    evidence = VerifiedEvidenceSet(
        items=(
            EvidenceItem(
                chunk_id="chunk-basic",
                document_id="doc-hwp",
                text="그리기 개체는 여러 개의 개체를 하나의 틀로 묶을 수 있기 때문에, 하나의 그림 코드에 하나 이상의 개체가 존재할 수 있다. 파일상에는 다음과 같은 구조로 저장된다.",
                citation=CitationRecord(document_id="doc-hwp", chunk_id="chunk-basic", label="[1]", state=CitationState.VALID),
                relevance_score=0.146,
                source_path="/tmp/hwp-format.hwp",
                heading_path="그리기 개체 자료 구조 > 기본 구조",
            ),
            EvidenceItem(
                chunk_id="chunk-order",
                document_id="doc-hwp",
                text="파일상에서의 그리기 개체는 계층 구조 트리에 대한 preorder traversal 순서로 저장된다. 따라서 위와 같은 경우라면 다음과 같은 순서로 저장된다.",
                citation=CitationRecord(document_id="doc-hwp", chunk_id="chunk-order", label="[2]", state=CitationState.VALID),
                relevance_score=0.145,
                source_path="/tmp/hwp-format.hwp",
                heading_path="그리기 개체 자료 구조 > 저장되는 개체의 순서",
            ),
        ),
        query_fragments=(TypedQueryFragment(text="한글 문서 8 형식에서 그리기 개체 자료에서 기본 구조에 대해 설명해줘", language="ko", query_type="keyword"),),
    )

    response = _build_stub_grounded_response(
        "한글 문서 8 형식에서 그리기 개체 자료에서 기본 구조에 대해 설명해줘",
        evidence,
    )

    assert "하나의 그림 코드에 하나 이상의 개체가 존재할 수 있다." in response
    assert "preorder traversal" not in response
    assert "파일상에는 다음과 같은 구조로 저장된다." in response


def test_stub_document_response_skips_path_heavy_segments_when_brand_term_overlaps() -> None:
    evidence = VerifiedEvidenceSet(
        items=(
            EvidenceItem(
                chunk_id="chunk-brochure",
                document_id="doc-brochure",
                text=(
                    "[Slide 1] DEVELOPER PRODUCTIVITY TOOL ProjectHub macOS용 올인원 프로젝트 관리 도구 "
                    "AI 기반 자율 코딩 시스템 내장 프로젝트 관리 AI 코드 생성 내장 터미널"
                ),
                citation=CitationRecord(document_id="doc-brochure", chunk_id="chunk-brochure", label="[1]", state=CitationState.VALID),
                relevance_score=0.16,
                source_path="/tmp/ProjectHub_Brochure.pptx",
                heading_path="",
            ),
            EvidenceItem(
                chunk_id="chunk-json",
                document_id="doc-json",
                text=(
                    "codingstudio/__PROJECTHUB__/JARVIS/.projecthub/workspace/TASK/round_2/claude_opinion.md#L470)).\", "
                    "\"The analysis mixes security/access-control facts with performance sizing and presents some quantitative thresholds as if measured truth."
                ),
                citation=CitationRecord(document_id="doc-json", chunk_id="chunk-json", label="[2]", state=CitationState.VALID),
                relevance_score=0.09,
                source_path="/tmp/TASK-E93DF600.json",
                heading_path="",
            ),
        ),
        query_fragments=(TypedQueryFragment(text="projecthub brochure introduction", language="en", query_type="keyword"),),
    )

    response = _build_stub_grounded_response(
        "ProjectHub 브로셔에서 ProjectHub를 어떻게 소개하나요?",
        evidence,
    )

    assert "ProjectHub macOS용 올인원 프로젝트 관리 도구" in response
    assert "claude_opinion.md#L470" not in response


def test_stub_document_response_uses_query_fragment_path_match_for_brochure_file() -> None:
    evidence = VerifiedEvidenceSet(
        items=(
            EvidenceItem(
                chunk_id="chunk-brochure",
                document_id="doc-brochure",
                text="[Slide 1] DEVELOPER PRODUCTIVITY TOOL ProjectHub macOS용 올인원 프로젝트 관리 도구 AI 기반 자율 코딩 시스템 내장",
                citation=CitationRecord(document_id="doc-brochure", chunk_id="chunk-brochure", label="[1]", state=CitationState.VALID),
                relevance_score=0.16,
                source_path="/tmp/ProjectHub_Brochure.pptx",
                heading_path="",
            ),
            EvidenceItem(
                chunk_id="chunk-help",
                document_id="doc-swift",
                text='Button(String(localized: "ProjectHub Help")) {',
                citation=CitationRecord(document_id="doc-swift", chunk_id="chunk-help", label="[2]", state=CitationState.VALID),
                relevance_score=0.11,
                source_path="/tmp/ProjectHubApp.swift",
                heading_path="",
            ),
        ),
        query_fragments=(TypedQueryFragment(text="projecthub brochure", language="en", query_type="keyword"),),
    )

    response = _build_stub_grounded_response(
        "ProjectHub 브로셔에서 ProjectHub를 어떻게 소개하나요?",
        evidence,
    )

    assert "ProjectHub macOS용 올인원 프로젝트 관리 도구" in response
    assert 'ProjectHub Help' not in response


def test_stub_document_response_prefers_matching_brochure_feature_section_within_chunk() -> None:
    evidence = VerifiedEvidenceSet(
        items=(
            EvidenceItem(
                chunk_id="chunk-brochure-features",
                document_id="doc-brochure",
                text=(
                    "[Slide 1]\n"
                    "DEVELOPER PRODUCTIVITY TOOL\n"
                    "ProjectHub\n"
                    "macOS용 올인원 프로젝트 관리 도구\n\n"
                    "[Slide 5]\n"
                    "FEATURES\n"
                    "개발자를 위한 모든 기능\n"
                    "코드 다이어그램\n"
                    "플로우 차트, 클래스 다이어그램, ER 다이어그램 자동 생성\n"
                    "파일 브라우저\n"
                    "트리 뷰, 와일드카드 검색, 20+ 언어 구문 강조\n"
                    "Git 통합\n"
                    "상태 표시, 커밋 히스토리, 브랜치 관리를 UI에서\n"
                ),
                citation=CitationRecord(document_id="doc-brochure", chunk_id="chunk-brochure-features", label="[1]", state=CitationState.VALID),
                relevance_score=0.91,
                source_path="/tmp/ProjectHub_Brochure.pptx",
                heading_path="",
            ),
        ),
        query_fragments=(TypedQueryFragment(text="projecthub_brochure 개발자를 위한 기능", language="ko", query_type="keyword"),),
    )

    response = _build_stub_grounded_response(
        "projecthub_brochure 에서 개발자를 위한 기능에는 어떤 것이 있나요 ?",
        evidence,
    )

    assert "개발자를 위한 모든 기능" in response
    assert "코드 다이어그램" in response
    assert "DEVELOPER PRODUCTIVITY TOOL" not in response
