from __future__ import annotations

import unicodedata
from pathlib import Path

from jarvis.contracts import CitationRecord, CitationState, EvidenceItem, TypedQueryFragment, VerifiedEvidenceSet
from jarvis.core.planner import Planner, QueryAnalysis
from jarvis.retrieval.regression_runner import load_regression_cases, run_regression_suite


def test_load_regression_cases_reads_fixture() -> None:
    fixture_path = (
        Path(__file__).resolve().parents[1]
        / "fixtures"
        / "retrieval_regression_v1.json"
    )

    cases = load_regression_cases(fixture_path)

    assert len(cases) >= 30
    assert any(case.expected_retrieval_task == "document_qa" for case in cases)
    assert any(case.expected_retrieval_task == "table_lookup" for case in cases)


def test_run_regression_suite_scores_task_and_source_accuracy() -> None:
    planner = Planner(lightweight_backend=None)
    cases = [
        load_regression_cases(
            Path(__file__).resolve().parents[1] / "fixtures" / "retrieval_regression_v1.json"
        )[0],
        load_regression_cases(
            Path(__file__).resolve().parents[1] / "fixtures" / "retrieval_regression_v1.json"
        )[8],
    ]

    def retrieve_fn(query: str, analysis: QueryAnalysis) -> VerifiedEvidenceSet:
        if analysis.retrieval_task == "table_lookup":
            text = "Day=3 | Lunch=닭가슴살+현미밥1/3+김2장"
            source_path = "/tmp/14day_diet_supplements_final.xlsx"
            heading_path = "table-row-Diet-2"
        else:
            text = "그리기 개체 자료 구조 기본 구조 그리기 개체는 여러 개의 개체를 하나의 틀로 묶을 수 있다."
            source_path = "/tmp/한글문서파일형식_revision1.1_20110124.hwp"
            heading_path = "문서 구조 > 그리기 개체 자료 구조 > 기본 구조"
        item = EvidenceItem(
            chunk_id="chunk-1",
            document_id="doc-1",
            text=text,
            citation=CitationRecord(
                document_id="doc-1",
                chunk_id="chunk-1",
                label="[1]",
                state=CitationState.VALID,
            ),
            relevance_score=1.0,
            source_path=source_path,
            heading_path=heading_path,
        )
        return VerifiedEvidenceSet(
            items=(item,),
            query_fragments=(TypedQueryFragment(text=query, language="ko", query_type="keyword"),),
        )

    report = run_regression_suite(cases=cases, planner=planner, retrieve_fn=retrieve_fn)

    assert report.total_cases == 2
    assert report.task_accuracy == 1.0
    assert report.source_accuracy == 1.0
    assert report.section_accuracy == 1.0
    assert report.row_accuracy == 1.0


def test_run_regression_suite_normalizes_unicode_source_and_heading_matches() -> None:
    planner = Planner(lightweight_backend=None)
    case = load_regression_cases(
        Path(__file__).resolve().parents[1] / "fixtures" / "retrieval_regression_v1.json"
    )[0]

    decomposed_path = "/tmp/" + unicodedata.normalize(
        "NFD",
        "한글문서파일형식_revision1.1_20110124.hwp",
    )
    decomposed_heading = unicodedata.normalize("NFD", "문서 구조 > 그리기 개체 자료 구조 > 기본 구조")
    decomposed_text = unicodedata.normalize(
        "NFD",
        "그리기 개체 자료 구조 기본 구조 그리기 개체는 여러 개의 개체를 하나의 틀로 묶을 수 있다.",
    )

    def retrieve_fn(query: str, analysis: QueryAnalysis) -> VerifiedEvidenceSet:
        item = EvidenceItem(
            chunk_id="chunk-1",
            document_id="doc-1",
            text=decomposed_text,
            citation=CitationRecord(
                document_id="doc-1",
                chunk_id="chunk-1",
                label="[1]",
                state=CitationState.VALID,
            ),
            relevance_score=1.0,
            source_path=decomposed_path,
            heading_path=decomposed_heading,
        )
        return VerifiedEvidenceSet(
            items=(item,),
            query_fragments=(TypedQueryFragment(text=query, language="ko", query_type="keyword"),),
        )

    report = run_regression_suite(cases=[case], planner=planner, retrieve_fn=retrieve_fn)

    assert report.source_accuracy == 1.0
    assert report.section_accuracy == 1.0
