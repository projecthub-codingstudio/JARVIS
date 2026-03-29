# Retrieval Consensus Proposal

Date: 2026-03-27

Related documents:

- [2026-03-27-retrieval-algorithm-comparison.md](/Users/codingstudio/__PROJECTHUB__/JARVIS/alliance_20260317_130542/docs/superpowers/specs/2026-03-27-retrieval-algorithm-comparison.md)
- [2026-03-27-retrieval-research-review.md](/Users/codingstudio/__PROJECTHUB__/JARVIS/alliance_20260317_130542/docs/superpowers/specs/2026-03-27-retrieval-research-review.md)
- [2026-03-27-retrieval-comparison-conclusion.md](/Users/codingstudio/__PROJECTHUB__/JARVIS/alliance_20260317_130542/docs/superpowers/specs/2026-03-27-retrieval-comparison-conclusion.md)

## Purpose

This document is intended to help the team converge on a practical retrieval redesign plan for JARVIS.

It is not another research summary.
It is a decision-oriented consensus proposal based on the overlap between the two reviews.

## Consensus

The following points should be treated as agreed unless new evidence appears.

### 1. The main problem is architectural

Current retrieval failures are not best explained by a single bad heuristic or a single bad chunk score.

The shared diagnosis is:

- query interpretation is distributed across too many layers
- retrieval task boundaries are unclear
- ranking rules are compensating for structural weaknesses

Conclusion:

- the project should stop treating score boosting as the main solution path

### 2. Table retrieval must be separated from document retrieval

This is the strongest point of agreement.

Current failures such as:

- numeric mentions in prose queries drifting into table rows
- document questions retrieving diet spreadsheet rows

are direct evidence that retrieval backends are not sufficiently separated.

Conclusion:

- `TableRetriever` and `DocumentRetriever` must be split
- generic orchestrator logic should not perform table-specific inference

### 3. Query analysis must become a single explicit stage

Both reviews reject the current pattern where normalization, planner heuristics, retrieval helpers, and ranking rules all reinterpret the query.

Conclusion:

- planner output should explicitly include retrieval intent
- downstream retrieval should consume that intent, not re-decide it

### 4. Long technical documents need hierarchical retrieval

Flat chunk retrieval is not enough for HWP/PDF specification-style documents.

Conclusion:

- JARVIS should move toward `document -> section -> chunk` retrieval
- this can be phased, but it should be an explicit target architecture

### 5. Retrieval evaluation must be separated from answer quality

The current feedback loop relies too much on end-to-end assistant behavior.

Conclusion:

- source accuracy
- section accuracy
- row/column accuracy

should be measured independently from generation quality and TTS quality

## Proposed Working Agreement

The team should adopt the following working agreement.

### Agreement A. Short quick-fix phase is allowed

Low-risk validation work is acceptable before structural refactor, as long as it is tightly scoped.

Allowed examples:

- validate distance-to-score conversion
- validate reranker truncation limits
- isolate obviously dangerous boost rules

Not allowed:

- extending generic orchestrator heuristics to solve new retrieval regressions
- adding more domain-specific routing logic into low-level retrieval code

### Agreement B. Structural refactor starts immediately after quick validation

The quick-fix phase must not become an indefinite tuning phase.

Transition criterion:

- once obvious low-cost bugs are checked, the project moves to retrieval-task routing and backend separation

### Agreement C. Advanced retrieval upgrades come after task boundaries are clean

This includes:

- contextual retrieval
- parent-child chunking
- stronger rerankers
- RAPTOR-like or TreeRAG-like indexing

Reason:

- otherwise their measured benefit will be confounded by routing and backend-mixing errors

## Proposed Decisions

### Decision 1. Adopt `retrieval_task` as the new planner contract

Proposed minimum schema:

```json
{
  "retrieval_task": "document_qa",
  "entities": {
    "document": "한글문서 파일형식",
    "topic": "그리기 개체 자료 구조",
    "subtopic": "기본 구조"
  },
  "search_terms": [
    "한글문서 파일형식",
    "그리기 개체 자료 구조",
    "기본 구조"
  ]
}
```

Minimum task set:

- `document_qa`
- `table_lookup`
- `code_lookup`
- `multi_doc_qa`
- `live_data_request`

### Decision 2. Split retrievers by knowledge type

Planned split:

- `DocumentRetriever`
- `TableRetriever`
- `CodeRetriever`

Short-term compromise is allowed:

- same physical index
- different retrieval logic

Long-term target:

- separate retrieval backend behavior even if storage remains partially shared

### Decision 3. Keep quick-fix scope intentionally narrow

Approved quick-fix checks:

1. distance-to-score conversion validation
2. reranker truncation validation
3. removal or quarantine of the most dangerous boost rules

Anything beyond that should be considered refactor work, not quick-fix work.

### Decision 4. Build retrieval regression tests in parallel with refactor

This should start earlier than originally planned.

Recommended initial gold set size:

- 30 to 50 queries

Minimum coverage:

- document section lookup
- table row/column lookup
- mixed greeting plus task query
- numeric mention inside prose query
- STT corruption variants

## Open Questions

The following items still need explicit team choice.

### 1. Planner routing implementation path

Options:

- heuristic router first, LLM router later
- LLM router first, heuristic fallback

Recommendation:

- heuristic router for the first transition
- LLM-backed router after schema and evaluation stabilize

Reason:

- this reduces moving parts during backend separation

### 2. Table retriever storage strategy

Options:

- separate table index immediately
- shared index with separate retrieval logic first

Recommendation:

- shared index first, separate retrieval logic first
- separate storage only if metrics show interference remains

Reason:

- lower migration cost
- faster validation

### 3. Reranker upgrade timing

Recommendation:

- do not switch reranker before routing and retriever split are in place

Reason:

- otherwise quality gain attribution becomes noisy

## Recommended Execution Order

### Step 1

Perform quick validation checks only.

### Step 2

Add planner `retrieval_task` output.

### Step 3

Extract table retrieval logic out of generic orchestrator flow.

### Step 4

Introduce `DocumentRetriever` and `TableRetriever`.

### Step 5

Create retrieval regression dataset and run it continuously.

### Step 6

Benchmark reranker/contextual retrieval/chunking upgrades after structural boundaries are stable.

## Final Recommendation

The team should converge on this principle:

`Quick validation first, but structural routing and retriever separation must begin immediately after.`

This resolves the difference between:

- the structure-first argument
- the optimization-first argument

without allowing the project to drift back into indefinite heuristic tuning.
