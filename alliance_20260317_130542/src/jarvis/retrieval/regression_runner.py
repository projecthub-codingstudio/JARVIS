"""Retrieval regression runner utilities."""
from __future__ import annotations

import json
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable

from jarvis.contracts import EvidenceItem, VerifiedEvidenceSet
from jarvis.core.planner import QueryAnalysis


@dataclass(frozen=True)
class RetrievalRegressionCase:
    case_id: str
    query: str
    expected_retrieval_task: str
    category: str
    expected_source_suffix: str = ""
    expected_heading_keywords: tuple[str, ...] = ()
    expected_row: str = ""
    expected_rows: tuple[str, ...] = ()
    expected_field: str = ""
    expected_fields: tuple[str, ...] = ()


@dataclass(frozen=True)
class RetrievalRegressionResult:
    case_id: str
    category: str
    task_ok: bool
    source_ok: bool
    section_ok: bool
    row_ok: bool
    top_source_path: str
    retrieval_task: str

    @property
    def passed(self) -> bool:
        return self.task_ok and self.source_ok and self.section_ok and self.row_ok

    def to_dict(self) -> dict[str, object]:
        return {
            "case_id": self.case_id,
            "category": self.category,
            "passed": self.passed,
            "task_ok": self.task_ok,
            "source_ok": self.source_ok,
            "section_ok": self.section_ok,
            "row_ok": self.row_ok,
            "top_source_path": self.top_source_path,
            "retrieval_task": self.retrieval_task,
        }


@dataclass(frozen=True)
class RetrievalRegressionReport:
    total_cases: int
    passed_cases: int
    task_accuracy: float
    source_accuracy: float
    section_accuracy: float
    row_accuracy: float
    results: tuple[RetrievalRegressionResult, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "total_cases": self.total_cases,
            "passed_cases": self.passed_cases,
            "pass_rate": _ratio(self.passed_cases, self.total_cases),
            "task_accuracy": self.task_accuracy,
            "source_accuracy": self.source_accuracy,
            "section_accuracy": self.section_accuracy,
            "row_accuracy": self.row_accuracy,
            "results": [result.to_dict() for result in self.results],
        }


def load_regression_cases(path: Path) -> list[RetrievalRegressionCase]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    cases: list[RetrievalRegressionCase] = []
    for item in payload["queries"]:
        cases.append(
            RetrievalRegressionCase(
                case_id=str(item["id"]),
                query=str(item["query"]),
                expected_retrieval_task=str(item["expected_retrieval_task"]),
                category=str(item["category"]),
                expected_source_suffix=str(item.get("expected_source_suffix", "")),
                expected_heading_keywords=tuple(item.get("expected_heading_keywords", []) or ()),
                expected_row=str(item.get("expected_row", "")),
                expected_rows=tuple(item.get("expected_rows", []) or ()),
                expected_field=str(item.get("expected_field", "")),
                expected_fields=tuple(item.get("expected_fields", []) or ()),
            )
        )
    return cases


def run_regression_suite(
    *,
    cases: Iterable[RetrievalRegressionCase],
    planner: object,
    retrieve_fn: Callable[[str, QueryAnalysis], VerifiedEvidenceSet],
) -> RetrievalRegressionReport:
    results: list[RetrievalRegressionResult] = []
    for case in cases:
        analysis = planner.analyze(case.query)
        evidence = retrieve_fn(case.query, analysis)
        results.append(_evaluate_case(case, analysis, evidence))

    total_cases = len(results)
    passed_cases = sum(1 for result in results if result.passed)
    task_accuracy = _ratio(sum(1 for result in results if result.task_ok), total_cases)
    source_accuracy = _ratio(sum(1 for result in results if result.source_ok), total_cases)
    section_accuracy = _ratio(sum(1 for result in results if result.section_ok), total_cases)
    row_accuracy = _ratio(sum(1 for result in results if result.row_ok), total_cases)
    return RetrievalRegressionReport(
        total_cases=total_cases,
        passed_cases=passed_cases,
        task_accuracy=task_accuracy,
        source_accuracy=source_accuracy,
        section_accuracy=section_accuracy,
        row_accuracy=row_accuracy,
        results=tuple(results),
    )


def _evaluate_case(
    case: RetrievalRegressionCase,
    analysis: QueryAnalysis,
    evidence: VerifiedEvidenceSet,
) -> RetrievalRegressionResult:
    items = list(evidence.items)
    top_source_path = items[0].source_path if items and items[0].source_path else ""

    task_ok = analysis.retrieval_task == case.expected_retrieval_task
    source_ok = _source_ok(case, items)
    section_ok = _section_ok(case, items)
    row_ok = _row_ok(case, items)

    return RetrievalRegressionResult(
        case_id=case.case_id,
        category=case.category,
        task_ok=task_ok,
        source_ok=source_ok,
        section_ok=section_ok,
        row_ok=row_ok,
        top_source_path=top_source_path,
        retrieval_task=analysis.retrieval_task,
    )


def _source_ok(case: RetrievalRegressionCase, items: list[EvidenceItem]) -> bool:
    if not case.expected_source_suffix:
        return True
    suffix = _normalize_text(case.expected_source_suffix)
    for item in items[:3]:
        if item.source_path and _normalize_text(item.source_path).endswith(suffix):
            return True
    return False


def _section_ok(case: RetrievalRegressionCase, items: list[EvidenceItem]) -> bool:
    if not case.expected_heading_keywords:
        return True
    for item in items[:3]:
        haystacks = [
            _normalize_text(item.heading_path or ""),
            _normalize_text(item.text or ""),
        ]
        if all(any(_normalize_text(keyword) in haystack for haystack in haystacks) for keyword in case.expected_heading_keywords):
            return True
    return False


def _row_ok(case: RetrievalRegressionCase, items: list[EvidenceItem]) -> bool:
    expected_rows = set(case.expected_rows)
    if case.expected_row:
        expected_rows.add(case.expected_row)
    expected_fields = set(case.expected_fields)
    if case.expected_field:
        expected_fields.add(case.expected_field)
    if not expected_rows and not expected_fields:
        return True

    top_text = _normalize_text(" ".join((item.text or "") for item in items[:3]))
    rows_ok = all(_normalize_text(row) in top_text for row in expected_rows) if expected_rows else True
    fields_ok = all(_normalize_text(field) in top_text for field in expected_fields) if expected_fields else True
    return rows_ok and fields_ok


def _ratio(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return numerator / denominator


def _normalize_text(value: str) -> str:
    return unicodedata.normalize("NFC", value).casefold()
