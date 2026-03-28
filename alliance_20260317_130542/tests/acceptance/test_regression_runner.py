from __future__ import annotations

from dataclasses import dataclass

from jarvis.acceptance.regression_runner import (
    MenuAcceptanceCase,
    load_menu_acceptance_cases,
    run_menu_acceptance_suite,
)


@dataclass(frozen=True)
class FakeRepairResult:
    display_text: str
    final_query: str


@dataclass(frozen=True)
class FakeCitation:
    full_source_path: str


@dataclass(frozen=True)
class FakeResponse:
    spoken_response: str
    citations: list[FakeCitation]


def test_load_menu_acceptance_cases_reads_fixture(tmp_path) -> None:
    fixture = tmp_path / "fixture.json"
    fixture.write_text(
        """
        {
          "queries": [
            {
              "id": "voice-1",
              "raw_transcript": "안녕하세요",
              "expected_display_text": "안녕하세요",
              "expected_final_query": "안녕하세요",
              "expected_spoken_response": "안녕하세요.",
              "expected_source_suffix": "kb.txt",
              "category": "greeting"
            }
          ]
        }
        """.strip(),
        encoding="utf-8",
    )

    cases = load_menu_acceptance_cases(fixture)

    assert len(cases) == 1
    assert cases[0].case_id == "voice-1"
    assert cases[0].expected_spoken_response == "안녕하세요."


def test_run_menu_acceptance_suite_scores_pipeline() -> None:
    cases = [
        MenuAcceptanceCase(
            case_id="voice-1",
            category="diet_slot_repair",
            raw_transcript="raw one",
            expected_display_text="display one",
            expected_final_query="query one",
            expected_spoken_response="spoken one",
            expected_source_suffix="diet.xlsx",
        ),
        MenuAcceptanceCase(
            case_id="voice-2",
            category="tail_noise",
            raw_transcript="raw two",
            expected_display_text="display two",
            expected_final_query="query two",
            expected_spoken_response="spoken two",
            expected_source_suffix="diet.xlsx",
        ),
    ]

    repair_map = {
        "raw one": FakeRepairResult(display_text="display one", final_query="query one"),
        "raw two": FakeRepairResult(display_text="wrong display", final_query="query two"),
    }
    ask_map = {
        "query one": FakeResponse("spoken one", [FakeCitation("/tmp/diet.xlsx")]),
        "query two": FakeResponse("wrong spoken", [FakeCitation("/tmp/diet.xlsx")]),
    }

    report = run_menu_acceptance_suite(
        cases=cases,
        repair_fn=lambda raw: repair_map[raw],
        ask_fn=lambda query: ask_map[query],
    )

    assert report.total_cases == 2
    assert report.passed_cases == 1
    assert report.display_accuracy == 0.5
    assert report.final_query_accuracy == 1.0
    assert report.spoken_accuracy == 0.5
    assert report.source_accuracy == 1.0
