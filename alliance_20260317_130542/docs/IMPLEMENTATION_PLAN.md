# JARVIS Implementation Plan

## Completed

- Hybrid retrieval with FTS, vector search, freshness checks, and evidence-backed generation
- Approval-gated export flow
- Metrics, health, audit, benchmark, and menu bar bridge
- Voice file mode, PTT once, and menu bar live loop
- Error thresholds, degraded mode, generation block, safe mode

## Current Stabilization Focus

1. Governor-driven runtime shaping
   - Context window reduction
   - Retrieved chunk count reduction
   - AC, battery, thermal, and indexing pressure policies
2. Indexing safety
   - Thermal/battery pause
   - SQLite lock retry
   - Read-only fallback on integrity failure
3. Observability hardening
   - Trace capture
   - More complete metric emit paths
4. Test hardening
   - Unit coverage for safety policies
   - Integration coverage for degraded/indexing paths

## Explicitly Deferred

- MeCab-ko default path
- Cross-encoder reranker
- Full automation tiers
- 90% branch coverage target as a release gate in the current repository state
