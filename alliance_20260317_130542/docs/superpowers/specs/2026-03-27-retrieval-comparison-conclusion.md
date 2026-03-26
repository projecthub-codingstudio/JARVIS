# Retrieval Comparison Conclusion

Date: 2026-03-27

Compared documents:

- [2026-03-27-retrieval-algorithm-comparison.md](/Users/codingstudio/__PROJECTHUB__/JARVIS/alliance_20260317_130542/docs/superpowers/specs/2026-03-27-retrieval-algorithm-comparison.md)
- [2026-03-27-retrieval-research-review.md](/Users/codingstudio/__PROJECTHUB__/JARVIS/alliance_20260317_130542/docs/superpowers/specs/2026-03-27-retrieval-research-review.md)

## Bottom Line

The two reviews are not contradictory.

- Claude's review is stronger on practical interventions and immediate optimization candidates.
- Codex's review is stronger on structural diagnosis and retrieval architecture boundaries.

The right direction for JARVIS is a hybrid plan:

1. apply a few low-risk retrieval fixes immediately
2. move quickly into retrieval-task routing and backend separation
3. only then upgrade rerankers and advanced retrieval techniques

## Where Both Reviews Strongly Agree

### 1. The current problem is structural, not just tuning

Both reviews conclude that current failures are not primarily caused by a single bad boost or a single bad chunk. The main issue is that intent interpretation, retrieval routing, and ranking compensation are mixed together.

Practical meaning:

- adding more score boosts will keep producing regressions
- retrieval task routing must become explicit

### 2. Table retrieval and prose retrieval must be separated

This is the most important agreement.

Both reviews independently identify that:

- spreadsheet/table lookups behave differently from document QA
- generic retrieval orchestration should not infer table row semantics from generic numeric mentions

Practical meaning:

- JARVIS should introduce `TableRetriever`
- `DocumentRetriever` should remain separate
- table logic should leave the generic orchestrator

### 3. Flat chunk retrieval is not enough for long technical documents

Both reviews point to hierarchical or context-aware retrieval as the right direction.

Practical meaning:

- HWP/PDF specifications should move toward:
  - document
  - section/heading
  - chunk
  retrieval

### 4. Query rewriting must be centralized

Both reviews reject distributed heuristic rewriting across many files.

Practical meaning:

- one planner stage should own query analysis
- downstream retrieval should consume structured output, not reinterpret intent again

## Where the Reviews Differ

### 1. Structure-first vs optimization-first

Codex emphasizes:

- retrieval-task routing
- retriever separation
- hierarchical retrieval

Claude emphasizes:

- quick fixes
- contextual retrieval
- reranker replacement
- implementation ROI

Assessment:

- Codex is more correct about the root cause
- Claude is more useful for low-risk early improvements

### 2. Research source profile

Codex review is more academically conservative.

- mostly peer-reviewed ACL/EMNLP/NAACL/EACL/OpenReview sources
- stronger architectural argument

Claude review is broader and more operational.

- includes industry writeups and implementation practices
- stronger shortlist of concrete upgrade candidates

Assessment:

- use Codex conclusions to decide architecture
- use Claude candidates to prioritize engineering experiments

## Recommended Decision

The project should not choose between the two reviews.

It should use this sequence:

### Phase A. Quick validation fixes

Keep this phase short and narrow.

- verify LanceDB distance-to-score behavior if still relevant
- verify reranker truncation limits
- reduce or isolate the most dangerous retrieval boosts

Why:

- these are low-cost checks
- they may remove some noise before larger refactors

### Phase B. Retrieval task routing

This is the real pivot point.

Add planner output such as:

```json
{
  "retrieval_task": "document_qa",
  "entities": {
    "document": "한글문서 파일형식",
    "topic": "그리기 개체 자료 구조",
    "subtopic": "기본 구조"
  }
}
```

Task values should include at least:

- `document_qa`
- `table_lookup`
- `code_lookup`
- `live_data_request`

### Phase C. Backend split

After routing exists:

- create `DocumentRetriever`
- create `TableRetriever`
- keep `CodeRetriever` or file-targeted retriever separate

This is the change most likely to eliminate the recent "11번" and "식단표 오염" failures.

### Phase D. Improve retrieval quality after boundaries are clean

Only after Phases B-C:

- benchmark stronger reranker candidates
- test contextual retrieval
- test parent-child or hierarchical chunking
- evaluate coarse-to-fine retrieval

This avoids measuring reranker gains on top of a broken routing model.

## What Should Not Happen Next

The project should avoid these patterns:

- adding more domain terms directly into generic orchestrator logic
- fixing retrieval drift by answer-side formatting
- using evidence boosts to simulate missing routing
- mixing table row inference into generic numeric document queries

## Most Important Combined Conclusion

If only one change can be prioritized, it should be:

`planner retrieval_task -> DocumentRetriever/TableRetriever split`

That is the strongest overlap between both reviews and the highest-leverage correction for the failures currently observed in JARVIS.
