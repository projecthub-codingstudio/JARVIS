# JARVIS Retrieval Final Consensus

Date: 2026-03-27

Basis:

- [2026-03-27-retrieval-consensus.md](/Users/codingstudio/__PROJECTHUB__/JARVIS/alliance_20260317_130542/docs/superpowers/specs/2026-03-27-retrieval-consensus.md)
- [2026-03-27-retrieval-consensus-proposal.md](/Users/codingstudio/__PROJECTHUB__/JARVIS/alliance_20260317_130542/docs/superpowers/specs/2026-03-27-retrieval-consensus-proposal.md)
- [2026-03-27-retrieval-algorithm-comparison.md](/Users/codingstudio/__PROJECTHUB__/JARVIS/alliance_20260317_130542/docs/superpowers/specs/2026-03-27-retrieval-algorithm-comparison.md)

## Decision

Further discussion is not required before moving into implementation planning.

A final consensus is possible now because:

- the architectural diagnosis is already aligned
- the most important execution order is aligned
- the remaining disagreements can be downgraded from philosophical disagreements to implementation sequencing choices

In other words:

- core direction is agreed
- a few items remain experimental
- those items do not block the main retrieval refactor

## Final Agreed Principles

### 1. Retrieval must be redesigned structurally

The team agrees that current failures are not primarily caused by isolated ranking bugs.

The main problems are:

- intent leakage across layers
- table and prose retrieval mixing
- flat chunk retrieval on long technical documents
- score boosting compensating for missing routing and structure

### 2. Query analysis becomes a single explicit stage

Planner must become the owner of retrieval interpretation.

The planner must produce structured output that downstream retrieval consumes directly.

Minimum new contract:

- `retrieval_task`
- `entities`
- `search_terms`

### 3. Table retrieval and document retrieval are separated

This is mandatory.

Short-term:

- same physical storage is allowed
- retrieval logic must already be separated

Long-term:

- physical separation is allowed if metrics justify it

### 4. Quick fixes are allowed, but tightly bounded

Immediate validation work is allowed only for:

- score conversion validation
- reranker truncation validation
- quarantine/removal of obviously dangerous boosts

Quick fixes must not turn into extended heuristic tuning.

### 5. Retrieval evaluation starts early

The project will not wait until the end of the refactor to measure retrieval quality.

An initial regression set must be created early and used throughout the refactor.

### 6. Advanced retrieval improvements come after task boundaries are stable

This includes:

- reranker upgrades
- contextual retrieval rollout
- parent-child chunking
- RAPTOR-like tree indexing
- late interaction retrieval

These are important, but they must not substitute for routing and retriever separation.

## Resolution of Open Questions

### Q1. Two-stage router

Decision: **Agreed with adoption**

Adopt:

- heuristic fast router first
- LLM deep router on low confidence or ambiguous queries

Reason:

- lower latency on simple queries
- less operational risk during the first refactor phase
- consistent with the shared view that planner owns routing

### Q2. Logical strategy split vs physical retriever split

Decision: **Agreed with staged approach**

Adopt:

1. logical strategy split first
2. physical retriever split only if metrics show continued interference or performance bottlenecks

Reason:

- faster migration
- lower regression risk
- keeps future physical separation available

### Q3. Contextual Retrieval timing

Decision: **Deferred as an experiment, not blocked**

Consensus:

- Contextual Retrieval is promising
- but it is not part of the minimum structural consensus
- it may run as a background experiment track if it does not delay routing/refactor work

Reason:

- it can improve chunk representation
- but the project should not depend on it before routing and retriever boundaries are fixed

### Q4. Early gold test set

Decision: **Agreed with adoption**

Adopt:

- a minimum 30-query retrieval regression set at the start of implementation

Minimum coverage:

- document section lookup
- table row/column lookup
- mixed greeting plus task query
- numeric mention inside prose
- STT corruption cases

Reason:

- refactor effects must be measurable
- regressions must be detected early

### Q5. Task-specific dynamic RRF weights

Decision: **Deferred until routing exists**

Consensus:

- dynamic weighting is plausible
- but it should not be committed before `retrieval_task` routing exists and baseline metrics are available

Reason:

- otherwise it becomes another tuning layer without clean attribution

### Q6. Section-aware vs Parent-Child vs RAPTOR order

Decision: **Agreed with staged order**

Adopt this order:

1. section-aware retrieval
2. parent-child chunking
3. RAPTOR or deeper hierarchical indexing if still needed

Reason:

- section-aware retrieval fits current metadata and is the lowest-risk structural improvement
- parent-child chunking is a practical next enhancement
- RAPTOR is higher-cost and should follow only if evidence shows it is still needed

## Final Implementation Order

### Phase 1. Quick validation and regression baseline

- validate distance-to-score behavior
- validate reranker truncation limits
- isolate dangerous boost rules
- build the first 30-query retrieval regression set

### Phase 2. Planner routing

- add `retrieval_task` output
- implement two-stage routing
  - heuristic fast router
  - LLM router on low confidence
- centralize query rewriting into planner-owned analysis

### Phase 3. Retrieval strategy split

- introduce `DocumentStrategy`
- introduce `TableStrategy`
- introduce `CodeStrategy`
- remove table-specific inference from generic orchestrator logic

### Phase 4. Structural retrieval improvement

- implement section-aware document retrieval
- reduce evidence-layer boost rules
- benchmark retrieval quality against regression set

### Phase 5. Quality upgrades

- benchmark reranker replacement candidates
- evaluate parent-child chunking
- evaluate Contextual Retrieval experiment results
- decide whether dynamic RRF weighting is beneficial

### Phase 6. Advanced options

- evaluate RAPTOR only if section-aware plus parent-child is insufficient
- evaluate late-interaction retrieval only if corpus scale or retrieval difficulty requires it

## Final Rule

The project will follow this rule:

`No new domain-specific retrieval heuristics are added to the generic orchestrator path.`

If a retrieval problem appears:

- first ask whether it is a routing problem
- then ask whether it is a retriever-boundary problem
- only then consider bounded fallback heuristics

## Final Summary

The final consensus is:

- quick validation first
- planner-owned retrieval routing next
- logical retriever separation immediately after
- early regression testing in parallel
- advanced retrieval upgrades only after structural boundaries are stable

This is sufficient to move from discussion to implementation planning.
