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
