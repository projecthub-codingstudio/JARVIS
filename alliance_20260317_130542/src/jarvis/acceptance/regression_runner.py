"""Acceptance regression runner for menu bar voice flows."""

from __future__ import annotations

import json
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable


@dataclass(frozen=True)
class MenuAcceptanceCase:
    case_id: str
    category: str
    raw_transcript: str
    expected_display_text: str
    expected_final_query: str
    expected_spoken_response: str
    expected_source_suffix: str = ""


@dataclass(frozen=True)
class MenuAcceptanceResult:
    case_id: str
    category: str
    display_ok: bool
    final_query_ok: bool
    spoken_ok: bool
    source_ok: bool
    actual_display_text: str
    actual_final_query: str
    actual_spoken_response: str
    top_source_path: str

    @property
    def passed(self) -> bool:
        return self.display_ok and self.final_query_ok and self.spoken_ok and self.source_ok

    def to_dict(self) -> dict[str, object]:
        return {
            "case_id": self.case_id,
            "category": self.category,
            "passed": self.passed,
            "display_ok": self.display_ok,
            "final_query_ok": self.final_query_ok,
            "spoken_ok": self.spoken_ok,
            "source_ok": self.source_ok,
            "actual_display_text": self.actual_display_text,
            "actual_final_query": self.actual_final_query,
            "actual_spoken_response": self.actual_spoken_response,
            "top_source_path": self.top_source_path,
        }


@dataclass(frozen=True)
class MenuAcceptanceReport:
    total_cases: int
    passed_cases: int
    display_accuracy: float
    final_query_accuracy: float
    spoken_accuracy: float
    source_accuracy: float
    results: tuple[MenuAcceptanceResult, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "total_cases": self.total_cases,
            "passed_cases": self.passed_cases,
            "pass_rate": _ratio(self.passed_cases, self.total_cases),
            "display_accuracy": self.display_accuracy,
            "final_query_accuracy": self.final_query_accuracy,
            "spoken_accuracy": self.spoken_accuracy,
            "source_accuracy": self.source_accuracy,
            "results": [result.to_dict() for result in self.results],
        }


def load_menu_acceptance_cases(path: Path) -> list[MenuAcceptanceCase]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    cases: list[MenuAcceptanceCase] = []
    for item in payload["queries"]:
        cases.append(
            MenuAcceptanceCase(
                case_id=str(item["id"]),
                category=str(item["category"]),
                raw_transcript=str(item["raw_transcript"]),
                expected_display_text=str(item["expected_display_text"]),
                expected_final_query=str(item["expected_final_query"]),
                expected_spoken_response=str(item["expected_spoken_response"]),
                expected_source_suffix=str(item.get("expected_source_suffix", "")),
            )
        )
    return cases


def run_menu_acceptance_suite(
    *,
    cases: Iterable[MenuAcceptanceCase],
    repair_fn: Callable[[str], object],
    ask_fn: Callable[[str], object],
) -> MenuAcceptanceReport:
    results: list[MenuAcceptanceResult] = []
    for case in cases:
        repaired = repair_fn(case.raw_transcript)
        final_query = str(getattr(repaired, "final_query", "") or "")
        display_text = str(getattr(repaired, "display_text", "") or "")
        response = ask_fn(final_query)
        actual_spoken = str(getattr(response, "spoken_response", "") or "")
        top_source_path = _extract_top_source_path(response)

        results.append(
            MenuAcceptanceResult(
                case_id=case.case_id,
                category=case.category,
                display_ok=_normalize_text(display_text) == _normalize_text(case.expected_display_text),
                final_query_ok=_normalize_text(final_query) == _normalize_text(case.expected_final_query),
                spoken_ok=_normalize_text(actual_spoken) == _normalize_text(case.expected_spoken_response),
                source_ok=_source_ok(case.expected_source_suffix, top_source_path),
                actual_display_text=display_text,
                actual_final_query=final_query,
                actual_spoken_response=actual_spoken,
                top_source_path=top_source_path,
            )
        )

    total_cases = len(results)
    passed_cases = sum(1 for result in results if result.passed)
    return MenuAcceptanceReport(
        total_cases=total_cases,
        passed_cases=passed_cases,
        display_accuracy=_ratio(sum(1 for result in results if result.display_ok), total_cases),
        final_query_accuracy=_ratio(sum(1 for result in results if result.final_query_ok), total_cases),
        spoken_accuracy=_ratio(sum(1 for result in results if result.spoken_ok), total_cases),
        source_accuracy=_ratio(sum(1 for result in results if result.source_ok), total_cases),
        results=tuple(results),
    )


def _extract_top_source_path(response: object) -> str:
    citations = getattr(response, "citations", None)
    if not isinstance(citations, list) or not citations:
        return ""
    first = citations[0]
    for attr_name in ("full_source_path", "source_path", "path"):
        value = getattr(first, attr_name, "")
        if isinstance(value, str) and value.strip():
            return value
    return ""


def _source_ok(expected_source_suffix: str, actual_source_path: str) -> bool:
    if not expected_source_suffix:
        return True
    return _normalize_text(actual_source_path).endswith(_normalize_text(expected_source_suffix))


def _ratio(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return numerator / denominator


def _normalize_text(value: str) -> str:
    return unicodedata.normalize("NFC", value).casefold()
