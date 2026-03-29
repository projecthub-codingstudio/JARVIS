"""Run menu bar acceptance regressions against the local runtime."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from jarvis.acceptance.regression_runner import (
    load_menu_acceptance_cases,
    run_menu_acceptance_suite,
)
from jarvis.app.runtime_context import build_runtime_context, shutdown_runtime_context
from jarvis.cli.menu_bridge import _run_query_in_context
from jarvis.transcript_repair import build_transcript_repair


def _default_fixture_path() -> Path:
    return Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "menu_acceptance_regression_v1.json"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run JARVIS menu acceptance regression suite")
    parser.add_argument(
        "--fixture",
        type=Path,
        default=_default_fixture_path(),
        help="Path to menu acceptance regression fixture JSON",
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

    cases = load_menu_acceptance_cases(args.fixture)
    context = build_runtime_context(
        model_id=args.model,
        knowledge_base_path=args.knowledge_base,
        start_watcher_enabled=False,
        start_background_backfill=False,
        allow_mlx=args.allow_mlx,
        data_dir=args.data_dir,
    )
    try:
        report = run_menu_acceptance_suite(
            cases=cases,
            repair_fn=build_transcript_repair,
            ask_fn=lambda query: _run_query_in_context(query=query, model_id=args.model, context=context),
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
                "display_accuracy": report.display_accuracy,
                "final_query_accuracy": report.final_query_accuracy,
                "spoken_accuracy": report.spoken_accuracy,
                "source_accuracy": report.source_accuracy,
                "output_path": str(args.output) if args.output is not None else "",
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
