# Session Query Learning System Design

**Date**: 2026-04-05
**Status**: Approved
**Goal**: Enable JARVIS to learn from in-session failure→success query refinement patterns, then inject entity hints into future similar queries — all independent of the generation LLM.

## Problem

When a user asks an underspecified or ambiguous question, JARVIS's `answerability_gate` abstains or asks for clarification. The user typically refines the query (e.g., adds row_ids, fields, dates) until an answer succeeds. Currently, this refinement knowledge is discarded — the same underspecified question fails again in future sessions.

The system must learn these refinement patterns so that:
1. Future similar underspecified queries receive automatic entity hints
2. The learning layer is **independent of the generation LLM** (EXAONE, Gemma 4, future models swap freely)
3. Learning uses **implicit signals only** (no user-facing "was this helpful?" prompts)

## Research Foundation

This design synthesizes validated techniques from:

| Source | Contribution |
|--------|--------------|
| **Intent-Aware Neural Query Reformulation** (arXiv 2507.22213, 2025) | In-session reformulation detection: `initial query → reformulated query → successful engagement` triples |
| **RQ-RAG** (arXiv 2404.00610) | Query refinement taxonomy: rewrite / decompose / disambiguate |
| **Query Reformulation Mining** (Springer Discover Computing 2010) | 4-class reformulation type classification with 92% accuracy |
| **Conversational Search Survey** (arXiv 2410.15576, 2024) | Use retrieval metrics (MRR, NDCG) as implicit success signals |

**Core insight from research**: Success = in-session engagement convergence. Within one session, if a query is reformulated and the final variant produces strong engagement (answer + citations), the pair is worth learning.

## Architecture

Three-layer design that decouples learning from the generation LLM:

```
┌─────────────────────────────────────────────────┐
│  Layer 3: Hint Injection (pre-Planner)          │
│  New query → similar-pattern lookup → hints     │
├─────────────────────────────────────────────────┤
│  Layer 2: Pattern Store (LanceDB + SQLite)      │
│  LearnedPattern records, BGE-M3 embedding index │
├─────────────────────────────────────────────────┤
│  Layer 1: Session Event Capture                 │
│  Capture every query outcome as an event.       │
│  On session close, detect failure→success pairs │
└─────────────────────────────────────────────────┘

Generation LLM (EXAONE / Gemma 4) only sees Layer 3's enriched prompt.
Swapping the generation LLM never invalidates learned patterns.
```

### Component Responsibilities

| Component | Responsibility | Depends On |
|-----------|---------------|------------|
| `SessionEventCapture` | Orchestrator hook records query, outcome, citations | answerability_gate |
| `ReformulationDetector` | Find in-session failure→success pairs | Research thresholds (§Detection) |
| `PatternExtractor` | Classify pairs into 4 reformulation types, extract entity hints | planner._classify_retrieval_task |
| `PatternStore` | Persist patterns (SQLite) + embeddings (LanceDB) | BGE-M3 embedding runtime |
| `PatternMatcher` | Vector search for similar patterns on new queries | BGE-M3, LanceDB |
| `HintInjector` | Merge learned hints into QueryAnalysis before planner runs | planner.QueryAnalysis |

## Data Model

### SQLite Tables (in existing `jarvis.db`)

```sql
-- Every query outcome gets captured here
CREATE TABLE session_events (
    event_id        TEXT PRIMARY KEY,
    session_id      TEXT NOT NULL,
    turn_id         TEXT NOT NULL,
    query_text      TEXT NOT NULL,
    retrieval_task  TEXT,                    -- "table_lookup", "document_qa", etc.
    entities_json   TEXT,                    -- {"row_ids":["3"],"fields":["dinner"]}
    outcome         TEXT NOT NULL,           -- "answer" | "abstain" | "clarify"
    reason_code     TEXT,                    -- "weak_evidence", "supported", etc.
    citation_paths  TEXT,                    -- JSON array of full_source_path
    confidence      REAL,
    created_at      INTEGER NOT NULL,        -- unix timestamp
    analyzed_at     INTEGER                  -- NULL until batch detector has processed this row
);
CREATE INDEX idx_session_events_session ON session_events(session_id, created_at);

-- Learned patterns extracted from reformulation pairs
CREATE TABLE learned_patterns (
    pattern_id          TEXT PRIMARY KEY,
    canonical_query     TEXT NOT NULL,         -- the successful final query
    failed_variants     TEXT,                  -- JSON array of prior failed queries
    retrieval_task      TEXT NOT NULL,
    entity_hints_json   TEXT NOT NULL,         -- entities extracted from the success
    reformulation_type  TEXT NOT NULL,         -- "specialization" | "error_correction" | "parallel_move" | "generalization"
    success_count       INTEGER DEFAULT 1,     -- number of times this pattern has been hit
    citation_paths      TEXT,                  -- documents referenced when success was recorded
    created_at          INTEGER NOT NULL,
    last_used_at        INTEGER NOT NULL
);
CREATE INDEX idx_patterns_task ON learned_patterns(retrieval_task);
CREATE INDEX idx_patterns_last_used ON learned_patterns(last_used_at);
```

### LanceDB Collection (in existing `vectors.lance`)

```python
# Collection: pattern_embeddings
# One row per learned_pattern
{
    "pattern_id": "pattern-abc123",
    "embedding": [1024 floats],       # BGE-M3 embedding of canonical_query
    "retrieval_task": "table_lookup", # used as pre-filter during search
}
```

## Detection Algorithm

Runs as a periodic batch job every 10 minutes (background scheduler), processing all `session_events` rows not yet analyzed. Each event has an `analyzed_at` timestamp column added; the batch job selects rows where `analyzed_at IS NULL` and are older than 5 minutes (to ensure the full 5-minute detection window is visible).

### Thresholds (research-grounded)

- **Temporal window**: 5 minutes between failure and success (Intent-Aware 2025 standard)
- **Semantic similarity**: cosine ≥ 0.5 between failure and success embeddings (paraphrase-detection floor)

### Algorithm

```python
def detect_reformulation_pairs(session_events: list[SessionEvent]) -> list[ReformulationPair]:
    events = sorted(session_events, key=lambda e: e.created_at)
    pairs = []

    for i, failure in enumerate(events):
        if failure.outcome not in ("abstain", "clarify"):
            continue

        for j in range(i + 1, len(events)):
            candidate = events[j]
            if candidate.created_at - failure.created_at > 300:  # 5 min
                break
            if candidate.outcome != "answer":
                continue

            sim = cosine_similarity(embed(failure.query_text), embed(candidate.query_text))
            if sim >= 0.5:
                pairs.append(ReformulationPair(
                    failure=failure,
                    success=candidate,
                    similarity=sim,
                ))
                break  # only the first success after each failure
    return pairs
```

### Reformulation Type Classification (Springer 2010 methodology)

Four classes, detected by comparing failure and success entities:

| Type | Detection Rule | Example | Learn? |
|------|---------------|---------|--------|
| **specialization** | success has more entities than failure | "식단" → "식단표 3일차 저녁" | ✓ yes |
| **generalization** | success has fewer entities than failure | "파이썬 3.11 typing" → "파이썬 typing" | ✗ no (info loss) |
| **error_correction** | similarity ≥ 0.85 AND entities identical | typo/spacing fix | ✓ yes |
| **parallel_move** | same retrieval_task, different entity values | "3일차" → "4일차" | ✓ yes |

Only `specialization`, `error_correction`, and `parallel_move` patterns are persisted.

## Hint Injection Algorithm

Runs before every planner call.

```python
def enrich_query_with_hints(query: str, session_id: str) -> QueryAnalysis:
    # 1. Baseline planner analysis
    baseline = planner._classify_retrieval_task(query, ...)

    # 2. Vector search over learned patterns
    query_emb = embed(query)
    candidates = lance_search(
        query_emb,
        top_k=3,
        filter=f"retrieval_task = '{baseline.retrieval_task}'",
    )

    # 3. Threshold filter (paraphrase-matching standard: 0.75+)
    matches = [c for c in candidates if c.score >= 0.75]
    if not matches:
        return baseline

    # 4. Merge entities from top match
    top = matches[0]
    stored = load_pattern(top.pattern_id)
    merged_entities = merge_entities(
        explicit=baseline.entities,   # explicit always wins
        learned=stored.entity_hints,
    )

    # 5. Track usage
    increment_pattern_usage(top.pattern_id)

    return baseline.replace(entities=merged_entities)
```

### Merge Safety Rules

- **Explicit wins**: If the user's query contains `row_ids=[3]`, the learned hint cannot override it
- **Hint provenance**: Merged entities carry a `__source="learned_pattern"` marker so that downstream components (and logs) can identify learned hints
- **Decay**: Patterns unused for 30 days receive score penalties during matching (recency-biased)

## Error Handling

| Scenario | Handling |
|----------|----------|
| BGE-M3 embedding failure | Log warning, skip hint injection, proceed with baseline |
| LanceDB search timeout (1s) | Skip, proceed with baseline (no user-visible error) |
| Pattern count exceeds 10,000 | LRU purge of oldest unused patterns |
| Contradicting patterns detected | Prefer higher `success_count`; quarantine losers |

## Privacy Policy

This system respects JARVIS's privacy-first principle:

- **Storage location**: `~/.jarvis-menubar/jarvis.db` (existing DB, local only)
- **Failed query storage**: User input is stored verbatim, but **never transmitted externally**
- **User control**: `POST /api/learned-patterns/forget` endpoint lets users delete all or specific patterns
- **TTL option**: Config-level `pattern_ttl_days` enables automatic expiration

## Testing Strategy

### Unit Tests

- `ReformulationDetector`: verify 5-minute window, similarity threshold, single-success-per-failure
- `PatternExtractor`: verify 4-class classification accuracy on hand-crafted pairs
- `HintInjector`: verify explicit-wins merge behavior

### Integration Tests (scenario-based)

**Scenario 1 — specialization learning**:
```
Turn 1: "다이어트 식단표 알려줘" → abstain (too broad)
Turn 2: "다이어트 식단표에서 3일차 저녁 메뉴" → answer ✓
Assertion: pattern stored with reformulation_type=specialization, row_ids hint captured

Next session:
Turn 1: "다이어트 식단표에서 5일차 저녁 메뉴" → hint-enriched → answer ✓
Assertion: pattern success_count incremented
```

**Scenario 2 — parallel_move**:
```
Turn 1: "식단 3일차 저녁" → answer
Turn 2: "식단 4일차 저녁" → answer
Assertion: pattern stored with reformulation_type=parallel_move

Next session:
Turn 1: "식단 7일차 저녁" → pattern matched → answer ✓
```

### Performance Targets

- **Detection overhead** (batch job): <100ms for batches with ≤10 events
- **Injection overhead** (per query): <50ms (BGE-M3 embed + LanceDB search)
- **Accuracy**: >90% success rate on queries matching learned patterns after one training instance

## File Structure

| File | Responsibility |
|------|---------------|
| `src/jarvis/learning/__init__.py` | Package root |
| `src/jarvis/learning/session_event.py` | `SessionEvent` dataclass |
| `src/jarvis/learning/event_capture.py` | Orchestrator hook |
| `src/jarvis/learning/reformulation_detector.py` | Pair detection |
| `src/jarvis/learning/pattern_extractor.py` | 4-class classification |
| `src/jarvis/learning/pattern_store.py` | SQLite + LanceDB persistence |
| `src/jarvis/learning/pattern_matcher.py` | Vector-search retrieval |
| `src/jarvis/learning/hint_injector.py` | Planner integration |
| `tests/unit/test_reformulation_detector.py` | Detection unit tests |
| `tests/unit/test_pattern_extractor.py` | Classification unit tests |
| `tests/unit/test_hint_injector.py` | Merge-rule unit tests |
| `tests/integration/test_learning_e2e.py` | End-to-end scenario tests |

## Not Changing

- Existing `answerability_gate.py` logic (we hook on its output, don't modify)
- Existing `planner.py` classification rules (we extend via hint injection)
- Existing `orchestrator.py` core flow (we add capture hook, one injection point)
- Generation LLM backends (EXAONE, Gemma 4) — completely untouched
- Evidence verification logic (CitationVerifier stays as-is)
