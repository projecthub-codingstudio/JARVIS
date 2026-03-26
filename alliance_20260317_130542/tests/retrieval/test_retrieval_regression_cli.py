from __future__ import annotations

import json
from pathlib import Path

from jarvis.cli.retrieval_regression import main
from jarvis.retrieval.regression_runner import RetrievalRegressionReport, RetrievalRegressionResult


class _FakePlanner:
    pass


class _FakeOrchestrator:
    _planner = _FakePlanner()

    def _retrieve_evidence(self, query: str, analysis: object) -> object:
        raise AssertionError("retrieve path should be stubbed in this unit test")


class _FakeContext:
    orchestrator = _FakeOrchestrator()


def test_retrieval_regression_cli_writes_report(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    fixture = tmp_path / "fixture.json"
    fixture.write_text(
        json.dumps(
            {
                "queries": [
                    {
                        "id": "doc-1",
                        "query": "기본 구조 설명",
                        "expected_retrieval_task": "document_qa",
                        "category": "document_section_lookup",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    output = tmp_path / "report.json"

    monkeypatch.setattr(
        "jarvis.cli.retrieval_regression.build_runtime_context",
        lambda **_: _FakeContext(),
    )
    monkeypatch.setattr(
        "jarvis.cli.retrieval_regression.shutdown_runtime_context",
        lambda context: None,
    )
    monkeypatch.setattr(
        "jarvis.cli.retrieval_regression.run_regression_suite",
        lambda **_: RetrievalRegressionReport(
            total_cases=1,
            passed_cases=1,
            task_accuracy=1.0,
            source_accuracy=1.0,
            section_accuracy=1.0,
            row_accuracy=1.0,
            results=(
                RetrievalRegressionResult(
                    case_id="doc-1",
                    category="document_section_lookup",
                    task_ok=True,
                    source_ok=True,
                    section_ok=True,
                    row_ok=True,
                    top_source_path="/tmp/doc.md",
                    retrieval_task="document_qa",
                ),
            ),
        ),
    )

    exit_code = main(
        [
            "--fixture",
            str(fixture),
            "--output",
            str(output),
            "--model",
            "stub",
        ]
    )

    assert exit_code == 0
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["passed_cases"] == 1
    assert payload["results"][0]["case_id"] == "doc-1"

    stdout = capsys.readouterr().out
    summary = json.loads(stdout)
    assert summary["pass_rate"] == 1.0
    assert summary["output_path"] == str(output)
