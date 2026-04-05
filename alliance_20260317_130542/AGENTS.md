# JARVIS Agent Notes

This file records operating rules for future AI/code agents working in this repo.

## Core Voice Pipeline

The menu bar voice flow is intentionally split into these stages:

1. `STT`
2. `transcript repair`
3. `display correction`
4. `final_query handoff`
5. `planner / retrieval`
6. `response rendering`
7. `spoken_response / TTS`

Do not collapse these stages together when fixing regressions.

## Source Of Truth Rules

- `raw_transcript` must remain recoverable.
- Semantic STT repair lives in Python, not Swift.
- The single source of truth for transcript repair is [`src/jarvis/transcript_repair.py`](src/jarvis/transcript_repair.py).
- Swift should call the backend `repair_transcript` service and use its `display_text` / `final_query`.
- `query_normalization` is for semantic normalization after repair, not for accumulating ad-hoc STT typo fixes.
- Swift may do lightweight UI-only cleanup such as whitespace compaction, but not domain repair logic.

## Regression Handling Policy

When a final answer is wrong, do not patch the nearest visible symptom by default.

Always classify the failure into exactly one primary stage first:

- `STT`
- `transcript_repair`
- `planner`
- `retrieval`
- `response_rendering`
- `spoken_response`
- `tts_playback`

Then:

1. Fix the owning stage only.
2. Avoid duplicating the same rule in Swift and Python.
3. Add a regression case for the failure before considering the work complete.

## What To Do When A User Reports A Wrong Final Answer

Use this sequence:

1. Capture `raw transcript`, `display text`, `final query`, final answer, and spoken response when available.
2. Determine which stage first became wrong.
3. Fix only that stage.
4. Add or update at least one regression fixture.
5. Re-run the relevant regression suite.

Do not treat a wrong final answer as just a TTS issue because TTS is often only exposing an earlier retrieval/routing failure.

## Proactive Coverage

If a failure pattern is repeatable, it should move from reactive debugging into a fixture-backed regression set.

Current proactive regression layers:

- Retrieval routing/source regression:
  [`tests/fixtures/retrieval_regression_v1.json`](tests/fixtures/retrieval_regression_v1.json)
- Menu voice acceptance regression:
  [`tests/fixtures/menu_acceptance_regression_v1.json`](tests/fixtures/menu_acceptance_regression_v1.json)

The acceptance fixture is the preferred place for cases shaped like:

- `raw_transcript -> expected_display_text`
- `raw_transcript -> expected_final_query`
- `raw_transcript -> expected_spoken_response`

The retrieval fixture is the preferred place for cases shaped like:

- `query -> expected_retrieval_task`
- `query -> expected source / row / field`

## Current Operating Decision

For recurring voice/menu-bar regressions, the default policy is:

- classify first
- repair at the owning stage
- add fixture coverage immediately

If the same failure type appears twice, promote it from an ad-hoc fix into a durable regression case and, if appropriate, a domain-slot repair rule.
