"""Run retrieval regression suites against a real JARVIS runtime."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from jarvis.app.runtime_context import build_runtime_context, shutdown_runtime_context
from jarvis.retrieval.regression_runner import load_regression_cases, run_regression_suite


def _default_fixture_path() -> Path:
    return Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "retrieval_regression_v1.json"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run JARVIS retrieval regression suite")
    parser.add_argument(
        "--fixture",
        type=Path,
        default=_default_fixture_path(),
        help="Path to retrieval regression fixture JSON",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Optional path to write the JSON report",
    )
    parser.add_argument(
        "--model",
        default="stub",
        help="Model id to use for runtime bootstrap. Default: stub",
    )
    parser.add_argument(
        "--knowledge-base",
        type=Path,
        default=None,
        help="Optional knowledge base directory override",
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=None,
        help="Optional runtime data directory override",
    )
    parser.add_argument(
        "--allow-mlx",
        action="store_true",
        help="Allow MLX backend during runtime bootstrap",
    )
    args = parser.parse_args(argv)

    cases = load_regression_cases(args.fixture)
    context = build_runtime_context(
        model_id=args.model,
        knowledge_base_path=args.knowledge_base,
        start_watcher_enabled=False,
        start_background_backfill=False,
        allow_mlx=args.allow_mlx,
        data_dir=args.data_dir,
    )
    try:
        report = run_regression_suite(
            cases=cases,
            planner=context.orchestrator._planner,  # type: ignore[attr-defined]
            retrieve_fn=lambda query, analysis: context.orchestrator._retrieve_evidence(query, analysis=analysis),
        )
    finally:
        shutdown_runtime_context(context)

    payload = report.to_dict()
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    print(
        json.dumps(
            {
                "total_cases": report.total_cases,
                "passed_cases": report.passed_cases,
                "pass_rate": payload["pass_rate"],
                "task_accuracy": report.task_accuracy,
                "source_accuracy": report.source_accuracy,
                "section_accuracy": report.section_accuracy,
                "row_accuracy": report.row_accuracy,
                "output_path": str(args.output) if args.output is not None else "",
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
