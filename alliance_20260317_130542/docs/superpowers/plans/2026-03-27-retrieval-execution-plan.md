# Retrieval Execution Plan

Date: 2026-03-27

Source of truth:

- [2026-03-27-retrieval-final-consensus.md](/Users/codingstudio/__PROJECTHUB__/JARVIS/alliance_20260317_130542/docs/superpowers/specs/2026-03-27-retrieval-final-consensus.md)

## Goal

Execute the agreed retrieval refactor without falling back into incremental heuristic patching.

This plan is implementation-oriented.
Each phase defines:

- scope
- deliverables
- file targets
- validation criteria

## Guardrails

These rules apply throughout implementation.

1. No new domain-specific retrieval heuristics in the generic orchestrator path.
2. No answer-formatting fixes used to mask retrieval failures.
3. Every retrieval change must be validated against a regression set.
4. Quick-fix scope must stay limited to explicitly approved items.

## Phase 1. Quick Validation and Baseline

### Scope

- validate obvious low-risk retrieval bugs
- establish a measurable baseline

### Tasks

1. Validate distance-to-score conversion in the current vector retrieval path.
2. Validate reranker truncation behavior and current max input length assumptions.
3. Identify and quarantine the most dangerous evidence boosts.
4. Create the first retrieval regression set.

### Deliverables

- validation note for vector score behavior
- validation note for reranker truncation
- initial regression dataset
- regression runner script

### Expected file targets

- [hybrid_search.py](/Users/codingstudio/__PROJECTHUB__/JARVIS/alliance_20260317_130542/src/jarvis/retrieval/hybrid_search.py)
- [vector_index.py](/Users/codingstudio/__PROJECTHUB__/JARVIS/alliance_20260317_130542/src/jarvis/retrieval/vector_index.py)
- [evidence_builder.py](/Users/codingstudio/__PROJECTHUB__/JARVIS/alliance_20260317_130542/src/jarvis/retrieval/evidence_builder.py)
- `tests/retrieval/...`
- `tests/fixtures/retrieval/...`

### Validation

- baseline retrieval regression run saved
- at least 30 initial gold queries available

## Phase 2. Planner Retrieval Task

### Scope

- make planner the owner of retrieval interpretation
- centralize query analysis

### Tasks

1. Define the `retrieval_task` schema.
2. Extend planner output with:
   - `retrieval_task`
   - `entities`
   - `search_terms`
   - `confidence`
3. Implement the heuristic fast router.
4. Add a low-confidence handoff contract for a future LLM router.
5. Move query rewriting responsibility into planner-owned analysis.

### Deliverables

- retrieval task schema
- updated planner contract
- router confidence policy

### Expected file targets

- [planner.py](/Users/codingstudio/__PROJECTHUB__/JARVIS/alliance_20260317_130542/src/jarvis/core/planner.py)
- [query_normalization.py](/Users/codingstudio/__PROJECTHUB__/JARVIS/alliance_20260317_130542/src/jarvis/query_normalization.py)
- planner tests

### Validation

- planner unit tests for:
  - document queries
  - table queries
  - code queries
  - mixed greeting plus task queries
  - ambiguous low-confidence queries

## Phase 3. Retrieval Strategy Split

### Scope

- separate retrieval behavior by knowledge type
- remove table-specific logic from generic orchestration

### Tasks

1. Introduce a retrieval strategy interface.
2. Implement:
   - `DocumentStrategy`
   - `TableStrategy`
   - `CodeStrategy`
3. Remove inline table row inference from generic orchestrator flow.
4. Route retrieval through planner-produced `retrieval_task`.

### Deliverables

- retrieval strategy abstraction
- strategy implementations
- orchestrator simplified to route rather than infer

### Expected file targets

- [orchestrator.py](/Users/codingstudio/__PROJECTHUB__/JARVIS/alliance_20260317_130542/src/jarvis/core/orchestrator.py)
- new retrieval strategy module(s) under `src/jarvis/retrieval/`
- related unit tests

### Validation

- no table-specific domain inference remains in generic orchestrator path
- regression set shows:
  - prose queries no longer leak into table rows
  - table queries still retrieve correct rows/fields

## Phase 4. Section-Aware Document Retrieval

### Scope

- improve long-document retrieval structurally

### Tasks

1. Extend document retrieval to use heading/section context explicitly.
2. Prefer section candidates before final chunk selection.
3. Reduce evidence-layer compensatory boosts once section-aware retrieval is active.

### Deliverables

- section-aware document retrieval behavior
- reduced evidence boost rules

### Expected file targets

- [evidence_builder.py](/Users/codingstudio/__PROJECTHUB__/JARVIS/alliance_20260317_130542/src/jarvis/retrieval/evidence_builder.py)
- document retrieval modules
- indexing metadata consumers

### Validation

- regression improvement on document section lookup
- fewer ranking-only patches required for long-document queries

## Phase 5. Retrieval Quality Upgrades

### Scope

- evaluate higher-leverage improvements only after routing boundaries are stable

### Tasks

1. Benchmark reranker alternatives.
2. Evaluate parent-child chunking.
3. Evaluate Contextual Retrieval experiment results.
4. Revisit dynamic RRF weighting using actual task-routed metrics.

### Deliverables

- benchmark report
- go/no-go decision for:
  - reranker replacement
  - parent-child chunking
  - contextual retrieval rollout
  - dynamic RRF weights

### Validation

- all decisions backed by regression set measurements

## Phase 6. Advanced Retrieval Options

### Scope

- only if prior phases still leave measurable gaps

### Tasks

1. Evaluate RAPTOR or equivalent hierarchical indexing.
2. Evaluate late-interaction retrieval if needed.
3. Evaluate physical retriever separation if logical separation is insufficient.

### Validation

- only proceed if earlier phases fail to meet agreed targets

## Regression Dataset Requirements

### Minimum categories

1. Document section lookup
2. Table row lookup
3. Table row plus field lookup
4. Mixed greeting plus task query
5. Numeric mention inside prose query
6. STT corruption variants
7. File/code lookup

### Minimum per-case labels

- query
- expected retrieval task
- expected source document
- expected section or row
- expected field if applicable

## Success Metrics

### After Phase 3

- no known table/prose cross-contamination cases in regression set
- planner retrieval task produced for all covered query classes

### After Phase 4

- document section accuracy materially improved over baseline
- evidence boosting reduced from being the primary correction mechanism

### After Phase 5

- benchmark-driven decisions available for reranker/chunking/context enrichment

## Immediate Next Actions

1. Create retrieval regression dataset skeleton.
2. Inspect current vector score conversion path.
3. Inspect current reranker truncation path.
4. Draft `retrieval_task` schema.

## Explicit Non-Goals

These are not part of the current execution plan:

- full GraphRAG adoption
- broad late-interaction rollout
- full physical index separation before logical routing is proven
- prompt-based answer-side masking of retrieval errors
