# Retrieval Phase 1 Validation

Date: 2026-03-27

Related plan:

- [2026-03-27-retrieval-execution-plan.md](/Users/codingstudio/__PROJECTHUB__/JARVIS/alliance_20260317_130542/docs/superpowers/plans/2026-03-27-retrieval-execution-plan.md)

## Scope

This note records the initial Phase 1 findings for:

- vector score behavior
- reranker truncation behavior
- retrieval regression baseline assets

## Finding 1. Vector score conversion needs validation, but is not the primary current bug

Current implementation:

- [vector_index.py](/Users/codingstudio/__PROJECTHUB__/JARVIS/alliance_20260317_130542/src/jarvis/retrieval/vector_index.py) maps LanceDB `_distance` to `score = max(0.0, 1.0 - distance)`.
- [hybrid_search.py](/Users/codingstudio/__PROJECTHUB__/JARVIS/alliance_20260317_130542/src/jarvis/retrieval/hybrid_search.py) does not currently use vector score magnitude in fusion. It uses vector rank only.

Implication:

- incorrect distance-to-score calibration is a real quality risk for future weighted retrieval
- but it is not the primary cause of the current retrieval failures, because current fusion is rank-based

Decision:

- keep this item in Phase 1 validation
- do not treat it as the main root cause of the recent document/table contamination bugs

## Finding 2. Reranker truncation was definitely wrong

Previous implementation:

- [reranker.py](/Users/codingstudio/__PROJECTHUB__/JARVIS/alliance_20260317_130542/src/jarvis/retrieval/reranker.py) truncated passage text at 512 characters before passing it to the cross-encoder

Why this is wrong:

- model limits are token-based, not character-based
- Korean text loses disproportionately more semantic content under a naive character cutoff
- this can remove the exact explanatory region that the reranker should compare

Action taken:

- removed the naive 512-character truncation
- left sequence truncation to the model tokenizer and the cross-encoder runtime

## Finding 3. Evidence boosting remains a known risk surface

Current evidence building still applies multiple boost and penalty rules in [evidence_builder.py](/Users/codingstudio/__PROJECTHUB__/JARVIS/alliance_20260317_130542/src/jarvis/retrieval/evidence_builder.py).

This is not fully addressed in Phase 1.

Current interpretation:

- some boosts are still temporarily useful
- but they remain compensatory logic, not a stable final retrieval design

Decision:

- quarantine and reduction of the most dangerous boosts remains part of ongoing Phase 1 work
- broader cleanup belongs after retrieval-task routing and retriever strategy split

## Baseline Assets Added

### Retrieval regression fixture

Added:

- [retrieval_regression_v1.json](/Users/codingstudio/__PROJECTHUB__/JARVIS/alliance_20260317_130542/tests/fixtures/retrieval_regression_v1.json)

Coverage includes:

- document section lookup
- table row/field lookup
- mixed greeting plus task queries
- numeric mention inside prose
- STT corruption variants
- live-data request routing

### Fixture validation tests

Added:

- [test_retrieval_regression_fixture.py](/Users/codingstudio/__PROJECTHUB__/JARVIS/alliance_20260317_130542/tests/retrieval/test_retrieval_regression_fixture.py)
- [test_regression_runner.py](/Users/codingstudio/__PROJECTHUB__/JARVIS/alliance_20260317_130542/tests/retrieval/test_regression_runner.py)
- [test_regression_runner_integration.py](/Users/codingstudio/__PROJECTHUB__/JARVIS/alliance_20260317_130542/tests/retrieval/test_regression_runner_integration.py)
- [test_retrieval_regression_cli.py](/Users/codingstudio/__PROJECTHUB__/JARVIS/alliance_20260317_130542/tests/retrieval/test_retrieval_regression_cli.py)

### Regression runner and saved baseline

Added:

- [regression_runner.py](/Users/codingstudio/__PROJECTHUB__/JARVIS/alliance_20260317_130542/src/jarvis/retrieval/regression_runner.py)
- [retrieval_regression.py](/Users/codingstudio/__PROJECTHUB__/JARVIS/alliance_20260317_130542/src/jarvis/cli/retrieval_regression.py)
- saved baseline report:
  [2026-03-27-retrieval-baseline-report.json](/Users/codingstudio/__PROJECTHUB__/JARVIS/alliance_20260317_130542/docs/superpowers/specs/2026-03-27-retrieval-baseline-report.json)

Baseline run used:

- fixture: `retrieval_regression_v1.json`
- knowledge base: `alliance_20260317_130542/knowledge_base`
- data dir: `alliance_20260317_130542/.jarvis-menubar`
- model: `stub`

Observed baseline:

- total cases: `40`
- passed cases: `40`
- pass rate: `1.0`
- task accuracy: `1.0`
- source accuracy: `1.0`
- section accuracy: `1.0`
- row accuracy: `1.0`

Interpretation:

- planner routing is stable across the initial fixture
- table/document separation is behaving correctly on the covered cases
- section-aware document retrieval is stable on the expanded 40-case baseline
- the saved baseline report can now serve as the regression gate for the next phases

## HWP Reindex Validation

Additional validation completed on the live menu-bar data directory:

- verified `hwp5proc` execution from
  `/Users/codingstudio/__PROJECTHUB__/JARVIS/alliance_20260317_130542/.venv/bin/hwp5proc`
- verified structured HWP parsing on
  [한글문서파일형식_revision1.1_20110124.hwp](/Users/codingstudio/__PROJECTHUB__/JARVIS/knowledge_base/한글문서파일형식_revision1.1_20110124.hwp)
- reindexed the live HWP document in
  [jarvis.db](/Users/codingstudio/__PROJECTHUB__/JARVIS/alliance_20260317_130542/.jarvis-menubar/jarvis.db)
- confirmed document chunks now include heading-aware entries such as:
  - `그리기 개체 자료 구조 > 기본 구조`

Important finding:

- after SQLite-only reindex, retrieval baseline temporarily dropped because stale LanceDB vectors for the old chunk set were still present
- removing the stale vectors for this HWP document restored the baseline to `40/40`

Implication:

- live reindexing must keep SQLite chunk replacement and LanceDB cleanup in sync
- parser improvements alone are not sufficient if old vectors remain queryable

### Reranker regression tests

Added:

- [test_reranker.py](/Users/codingstudio/__PROJECTHUB__/JARVIS/alliance_20260317_130542/tests/retrieval/test_reranker.py)

## Phase 1 Exit Criteria Status

- vector score path inspected: complete
- reranker truncation inspected: complete
- reranker truncation quick-fix applied: complete
- initial regression fixture created: complete
- regression runner added: complete
- baseline regression run saved: complete
- dangerous boost quarantine: partial

## Next Recommended Actions

1. continue expanding the regression set beyond 40 queries
2. reduce remaining evidence-layer compensation without regressing the saved baseline
3. start benchmark work for Phase 5 quality upgrades
