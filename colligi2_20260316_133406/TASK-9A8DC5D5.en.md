# Implementation Specification for Alliance Coding Directives

**Document Type**: Technical Architecture Document
**Company**: Colligi2
**Project**: Implementation Specification for Alliance Coding Directives
**Version**: 1.0
**Date**: 2026-03-16

---

## 1. Document Header

- Company: Colligi2
- Project: Implementation Specification for Alliance Coding Directives
- Document Title: Implementation Specification for Alliance Coding Directives
- Document Type: Technical Architecture and Implementation Specification
- Version: 1.0
- Target Environment: MacBook Pro 16, Apple M1 Max, Unified Memory 64GB
- Reference Time: 2026-03-16 Asia/Seoul

## 2. Document Purpose and Final Decisions

This document is a `closed-decision implementation specification` created so that Alliance can begin implementation immediately without additional analysis, as part of Colligi2's Implementation Specification for Alliance Coding Directives. Its purpose is not to explore possibilities, but to lock down — at the code level — what to build first, how to structure it, and what criteria to validate against.

The final decisions are as follows.

- The product definition is fixed as a `local-first personal workspace agent`.
- The MVP scope is limited to `selected folder indexing`, `document/code hybrid search`, `citation-based Korean Q&A`, `draft generation`, and `approval-gated limited export`.
- The default runtime is `MLX`, default Korean processing is `Kiwi`, search is `SQLite FTS5 + vector index + RRF`, and the default generation tier is a `14B-class model`.
- Generation is implemented as `Evidence-First Generation`. That is, the LLM is treated not as a free-form generator but as a `module that explains a verified evidence set`.
- Search is preceded by `Query Decomposition`, not simple string matching.
- The Governor is not an auxiliary feature but a `system operating constitution`. Memory is not treated as a fixed budget but as a behavioral contract that responds to OS pressure signals.
- Security is implemented via `Capability-based Security` rather than post-hoc blocking. Rather than controlling dangerous tools through a complex approval engine, they are removed from the MVP API surface entirely.
- Voice, always-on screen context, accessibility-based UI automation, general shell autonomous execution, and Full Disk Access as a default requirement are excluded.

## 3. Redefinition of the Problem to Solve

The original request was "concretize existing JARVIS technical documents into an implementation specification," but the actual problem from an implementation perspective is:

`Providing closed decisions and actionable contracts so that Alliance can write code along a single implementation path without falling back into comparison/exploration mode`

Therefore, this document follows these principles.

- Leave no open comparisons.
- Provide only one default implementation.
- Retain replaceability only through interfaces.
- Prioritize `Protocol`, `Dataclass`, `DDL`, `pytest`, and `metric contracts` over prose.
- Separate human approval responsibility from Alliance's implementation responsibility.

## 4. Product Scope

### 4.1 MVP Included Scope

- Read-only indexing based on selected folders
- Parsing of Markdown, text, code, and log files
- Document/code unified hybrid search
- Korean Q&A
- File path and line-based citations
- Draft generation
- Approval-gated `draft_export`
- Conversation log and task log storage
- Incremental indexing with freshness state tracking
- CLI REPL-based interface

### 4.2 MVP Excluded Scope

- Voice input/output
- Always-on screen capture
- Accessibility-based general UI automation
- General shell command autonomous execution
- External service dependencies by default
- Full-disk indexing
- Full Disk Access as a default requirement
- Broad automation of Mail, Finder, and browsers
- 30B+ model always-resident

## 5. Change Decision Log Compared to Original Technical Documents

The original JARVIS technical documents were strong in direction and risk awareness, but contained many items that the implementer would need to re-decide. This specification closes the following items.

| Item | Original Document Status | Final Decision |
|---|---|---|
| Generation model | Comparison of 14B/7.8B/30B candidates | Fixed to `14B-class default tier`; upper models allowed only via explicit promotion after Phase 2 |
| Korean processing | Comparison of Kiwi or MeCab-ko | Fixed to `Kiwi as default`; MeCab-ko retains only a replacement path contingent on re-entry conditions |
| Search quality strategy | Hybrid search adopted, but query processing lacked specificity | Concretized as `Typed Query Decomposition + FTS5 + vector + RRF` |
| Citation method | Some post-correction-oriented expressions existed | Changed to `VerifiedEvidenceSet input enforcement` |
| Security | Centered on approval-based execution principles | Adopted `dangerous tool non-exposure` as the primary security structure |
| Interface | Menu bar UI after CLI | MVP fixed to `CLI REPL` |
| Schema | Table-name-level suggestions | Concretized as DDL contracts including key columns and constraints |
| Observability | Mentioned as a separate tier | Added `observability/` module and required metric contracts |
| Failure operations | Failure criteria and halt criteria provided | Extended to cover runtime exceptions, index corruption, SQLite locks, model load failure response procedures |

## Colligi2 Generation Process

This document is not the result of a single AI writing at once, but a collective intelligence output produced through multiple AIs cross-validating the same topic in stages.

1. **Intent Reconstruction**: Reconstructed the actual goals, hidden constraints, and questions requiring validation behind the user's surface request.
2. **Stage Design**: Multiple AIs independently proposed analysis stages, and the final analysis structure was designed through research and merging.
3. **Multi-stage Discussion**: At each analysis stage, AIs exchanged opinions, evaluations, and counterarguments to organize issues and alternatives.
4. **Emergent Integration**: Rather than simply summarizing stage results, conflict points and new insights were collectively synthesized.
5. **Problem Redefinition**: Re-examined whether the original question was sufficiently precise, and corrected it to a more essential problem definition.
6. **Collective Document Authoring**: After cross-reviewing multiple drafts and reviews, the final document was produced through unified editing.

- Participating AIs: 4
- Final analysis stages: 14
- Total discussion rounds: 20
- Provider records excluded due to intermediate failures: 0

## 6. Architecture Invariants

The following items are not to be reinterpreted during implementation.

- No factual response is generated without a `VerifiedEvidenceSet`.
- Search always takes `query decomposition results` as input.
- The only permitted write operation is `draft_export`.
- `draft_export` never executes without approval.
- The Governor may be a Stub initially, but the interface is fixed on Day 0.
- Citation state uses only five states: `VALID`, `STALE`, `REINDEXING`, `MISSING`, `ACCESS_LOST`.
- File system freshness is treated as a core trust feature, not an auxiliary feature.
- A feature that cannot be observed is not considered a completed feature.

## 7. Implementation Architecture

### 7.1 Target Repository Structure

```text
pyproject.toml
src/jarvis/
  app/
    bootstrap.py
    config.py
  contracts/
    models.py
    protocols.py
    states.py
    errors.py
  core/
    orchestrator.py
    governor.py
    planner.py
    tool_registry.py
  retrieval/
    query_decomposer.py
    tokenizer_kiwi.py
    fts_index.py
    vector_index.py
    hybrid_search.py
    evidence_builder.py
    freshness.py
  indexing/
    parsers.py
    chunker.py
    file_watcher.py
    index_pipeline.py
    tombstone.py
  runtime/
    mlx_runtime.py
    model_router.py
    embedding_runtime.py
  memory/
    conversation_store.py
    task_log.py
  tools/
    read_file.py
    search_files.py
    draft_export.py
  observability/
    metrics.py
    tracing.py
    health.py
  cli/
    repl.py
    approval.py
sql/
  schema.sql
tests/
  contracts/
  unit/
  integration/
  retrieval/
  indexing/
  runtime/
  perf/
  e2e/
docs/
  DECISIONS.md
  IMPLEMENTATION_PLAN.md
```

### 7.2 Component Responsibilities

| Component | Responsibility | Input | Output |
|---|---|---|---|
| `Orchestrator` | Overall request flow control | User query, session state | Response, citations, execution plan |
| `QueryDecomposer` | Decompose query into symbol/literal/prose fragments | Raw query | `TypedQueryFragment[]` |
| `HybridSearch` | Combine FTS5, vector, and RRF | `TypedQueryFragment[]` | `RankedChunk[]` |
| `EvidenceBuilder` | Construct verified evidence set | `RankedChunk[]` | `VerifiedEvidenceSet` |
| `FreshnessManager` | Calculate citation state | File events, index state | `CitationState` |
| `ModelRouter` | Select model tier based on Governor state | Request type, system state | `RuntimeProfile` |
| `MLXRuntime` | Execute generation and embeddings | Prompt, evidence set | Generation result |
| `IndexPipeline` | Parsing, chunking, index updates | File events | Index change result |
| `ToolRegistry` | Expose only permitted tools | Approval state | Tool handle |
| `ApprovalCLI` | Approval-gated draft generation UX | Plan, diff, target path | Approval/rejection result |
| `MetricsCollector` | Metric collection | Runtime events | Time-series metrics |

## 8. Actionable Contracts

### 8.1 Required Protocols

- `TokenizerProtocol`
- `QueryDecomposerProtocol`
- `RetrieverProtocol`
- `EvidenceBuilderProtocol`
- `RuntimeProtocol`
- `GovernorProtocol`
- `ToolProtocol`
- `MetricsProtocol`

### 8.2 Required Dataclasses

- `UserQuery`
- `TypedQueryFragment`
- `ChunkRecord`
- `RankedChunk`
- `VerifiedEvidence`
- `VerifiedEvidenceSet`
- `CitationRef`
- `AssistantResponse`
- `RuntimeProfile`
- `SystemSnapshot`
- `DraftExportPlan`
- `ApprovalDecision`

### 8.3 Core Type Conventions

```python
@dataclass
class TypedQueryFragment:
    kind: Literal["symbol", "literal", "prose"]
    text: str
    normalized: str
    weight: float

@dataclass
class CitationRef:
    document_id: str
    chunk_id: str
    file_path: str
    start_line: int
    end_line: int
    state: Literal["VALID", "STALE", "REINDEXING", "MISSING", "ACCESS_LOST"]

@dataclass
class VerifiedEvidence:
    chunk_id: str
    file_path: str
    content: str
    content_hash: str
    start_line: int
    end_line: int
    score_lexical: float
    score_semantic: float
    score_rrf: float
    citation_state: str

@dataclass
class RuntimeProfile:
    tier: Literal["baseline", "elevated", "degraded"]
    max_context_tokens: int
    max_retrieved_chunks: int
    generation_timeout_ms: int
```

### 8.4 Interface Principles

- LLM input is restricted to `query + VerifiedEvidenceSet + response format conventions`.
- `VerifiedEvidence` must include at minimum `content_hash`, `line range`, and `citation_state`.
- Search always receives `TypedQueryFragment[]`. Raw query strings are never passed directly.
- The Governor is initially implemented as a pure function `SystemSnapshot -> RuntimeProfile`.
- Memory is treated not as a fixed allocation but as a behavioral contract responding to OS pressure signals.
- Tools can only call items in the `ToolRegistry` registered list.
- Phase 1 tools are limited to three: `read_file`, `search_files`, and `draft_export`.

## 9. Data Model and DDL Contracts

The following schemas are the minimum contracts that must be implemented as `sql/schema.sql` on Day 0.

### 9.1 `documents`

| Column | Type | Constraints | Description |
|---|---|---|---|
| `document_id` | TEXT | PK | Document identifier |
| `file_path` | TEXT | UNIQUE NOT NULL | Absolute path |
| `file_type` | TEXT | NOT NULL | md, py, txt, etc. |
| `file_size` | INTEGER | NOT NULL | Bytes |
| `mtime_epoch_ms` | INTEGER | NOT NULL | Modification time |
| `content_hash` | TEXT | NOT NULL | File hash |
| `index_state` | TEXT | NOT NULL | ACTIVE, DELETED, ACCESS_LOST |
| `last_indexed_at` | INTEGER | NOT NULL | Last indexed time |

### 9.2 `chunks`

| Column | Type | Constraints | Description |
|---|---|---|---|
| `chunk_id` | TEXT | PK | Chunk identifier |
| `document_id` | TEXT | FK NOT NULL | Document reference |
| `chunk_order` | INTEGER | NOT NULL | Order within document |
| `start_offset` | INTEGER | NOT NULL | Character start offset |
| `end_offset` | INTEGER | NOT NULL | Character end offset |
| `start_line` | INTEGER | NOT NULL | Start line |
| `end_line` | INTEGER | NOT NULL | End line |
| `content` | TEXT | NOT NULL | Chunk raw text |
| `content_hash` | TEXT | NOT NULL | Chunk hash |
| `embedding_ref` | TEXT | NULL | Vector storage reference |
| `citation_state` | TEXT | NOT NULL | VALID, STALE, etc. |
| `created_at` | INTEGER | NOT NULL | Creation time |

### 9.3 `citations`

| Column | Type | Constraints | Description |
|---|---|---|---|
| `citation_id` | TEXT | PK | Citation identifier |
| `response_id` | TEXT | NOT NULL | Response identifier |
| `chunk_id` | TEXT | FK NOT NULL | Referenced chunk |
| `file_path` | TEXT | NOT NULL | File path |
| `start_line` | INTEGER | NOT NULL | Start line |
| `end_line` | INTEGER | NOT NULL | End line |
| `quoted_hash` | TEXT | NOT NULL | Citation hash at time of quoting |
| `citation_state` | TEXT | NOT NULL | VALID, STALE, etc. |
| `created_at` | INTEGER | NOT NULL | Creation time |

### 9.4 `conversation_turns`

| Column | Type | Constraints | Description |
|---|---|---|---|
| `turn_id` | TEXT | PK | Turn identifier |
| `session_id` | TEXT | NOT NULL | Session identifier |
| `role` | TEXT | NOT NULL | user, assistant |
| `content` | TEXT | NOT NULL | Body text |
| `response_id` | TEXT | NULL | Response reference |
| `created_at` | INTEGER | NOT NULL | Creation time |

### 9.5 `task_logs`

| Column | Type | Constraints | Description |
|---|---|---|---|
| `task_id` | TEXT | PK | Task identifier |
| `task_type` | TEXT | NOT NULL | search, answer, draft_export |
| `status` | TEXT | NOT NULL | STARTED, SUCCEEDED, FAILED, BLOCKED |
| `error_code` | TEXT | NULL | Error code |
| `latency_ms` | INTEGER | NULL | Processing time |
| `metadata_json` | TEXT | NOT NULL | Additional metadata |
| `created_at` | INTEGER | NOT NULL | Creation time |

### 9.6 FTS and Auxiliary Indexes

- `chunk_terms_raw`: Raw tokens such as identifiers, filenames, and error strings
- `chunk_terms_ko`: Korean tokens based on Kiwi analysis results
- The FTS5 index includes `content`, `raw_terms`, `ko_terms`, and `file_path`.

## 10. Search and Generation Pipeline

### 10.1 Q&A Flow

1. The user enters a Korean query in the CLI.
2. `QueryDecomposer` decomposes the query into `symbol`, `literal`, and `prose` fragments.
3. `HybridSearch` performs FTS5 and vector search in parallel.
4. Top candidates are combined via RRF.
5. `FreshnessManager` calculates the `citation_state` for each chunk.
6. `EvidenceBuilder` constructs a `VerifiedEvidenceSet` with `VALID` chunks prioritized.
7. `Governor` selects a `RuntimeProfile` appropriate for the current system state.
8. `MLXRuntime` generates the answer based solely on the evidence set.
9. The response is output with file path and line range citations.
10. All steps are recorded in metrics and `task_logs`.

### 10.2 Approval-Gated Draft Generation Flow

1. The user requests something like "create a summary draft" or "save a document draft."
2. `Planner` generates a `DraftExportPlan`.
3. The CLI first displays the following information:
   - Target file path
   - Whether the file is a new creation or an overwrite
   - Summarized change contents
   - 20-line draft preview or diff
4. The user is prompted with `approve [y/N]`.
5. Upon approval, only `draft_export` is executed.
6. Upon rejection, no file write is performed.
7. Results are recorded in `task_logs` and `conversation_turns`.

### 10.3 `draft_export` Conventions

- Permitted paths: `drafts/` subdirectory under the user-specified working directory, or explicitly approved target files
- Default output format: UTF-8 text file
- Default behavior: New file creation
- Overwrite requires separate approval
- External transmission, deletion, and moving are not permitted

## 11. Governor and Resource Management Policy

The Governor may be a Stub in the initial MVP, but the interface and state transitions are fixed.

### 11.1 Input Metrics

- Memory pressure
- Swap usage
- CPU utilization
- Thermal state
- Power connection status
- Battery level
- Indexing queue length
- Model load success/failure state

### 11.2 States

- `baseline`: Normal response mode
- `elevated`: Power connected + resource headroom available
- `degraded`: Memory pressure, low battery, high thermal, repeated errors

### 11.3 Behavioral Rules

| State | Model | Retrieved Chunk Count | Context | Indexing |
|---|---|---|---|---|
| `elevated` | Default 14B, may promote to higher tier if needed | 10 | Maximum | Aggressive |
| `baseline` | Default 14B | 8 | Standard | Low priority |
| `degraded` | Maintain or reduce default 14B | 4 | Reduced | Paused or backed off |

### 11.4 Forced Reduction Conditions

- When swap is detected: upper model promotion is prohibited
- When thermal state rises: indexing backs off
- When battery is below 30%: long context is prohibited
- When model load fails 2 consecutive times: enter degraded state
- When SQLite lock occurs 3 consecutive times: write queue is halted

## 12. Security and Permission Design

### 12.1 Permission Ladder

1. Manual text input only
2. Selected folder read access
3. Limited `draft_export`
4. Limited app integration
5. Accessibility-based automation

The MVP implements only up to levels 2-3.

### 12.2 Capability-Based Constraints

- `read_file`: Read-only
- `search_files`: Index query only
- `draft_export`: Approval-gated file creation/overwrite, limited scope
- Deletion, moving, execution, and external transmission tools are not registered

### 12.3 Safety Policies

- Factual assertions without citations are prohibited
- `STALE` or `MISSING` citations display a warning in the response
- Zero unauthorized state changes
- Access to paths outside designated folders is prohibited
- All tools are halted when consecutive error thresholds are exceeded

## 13. Failure Modes and Exception Handling

A system that only implements the happy path cannot become a production-ready system. The following failure modes are handled explicitly.

### 13.1 Model Load Failure

- Symptoms: MLX model initialization failure, out of memory, file corruption
- Response:
  - 1st occurrence: Automatic retry
  - 2 consecutive: Enter `degraded` state
  - 3 consecutive: Block generation, switch to search-only mode
- User message: Generation model temporarily disabled; only search results are provided

### 13.2 SQLite Lock or Index Corruption

- Symptoms: `database is locked`, integrity errors
- Response:
  - Read queries: Immediate retry once
  - Write operations: Queued and deferred
  - If integrity check fails: Switch to read-only mode
  - Set `rebuild_index` flag and recommend re-indexing to the user
- Hard Kill Condition: 3 repeated locks + sustained write queue growth

### 13.3 Embedding Backlog Explosion

- Symptoms: Frequent file changes causing increasing re-embedding delays
- Response:
  - Prioritize recently modified files
  - Defer large files
  - Use existing index with `STALE` warning
  - Reduce queue in battery mode

### 13.4 File Access Permission Loss

- Symptoms: Selected folder moved, permissions revoked, external drive disconnected
- Response:
  - Transition to `ACCESS_LOST` state
  - Deactivate citations for affected documents
  - Guide the user to restore permissions

### 13.5 Consecutive Error Threshold

- If the same error code occurs 5 or more times within 5 minutes: halt tool invocations
- If model failure + index failure occur simultaneously within 10 minutes: switch to `safe mode`
- In `safe mode`: only search results are provided; generation and writing are disabled

## 14. Observability and Operational Metrics

### 14.1 Required Metrics

- `query_latency_ms`
- `ttft_ms`
- `retrieval_top5_hit`
- `citation_missing_rate`
- `citation_stale_rate`
- `trust_recovery_time_ms`
- `index_lag_ms`
- `swap_detected_count`
- `model_load_failure_count`
- `sqlite_lock_count`
- `draft_export_approval_rate`

### 14.2 Logging Principles

- Use structured logs (JSON)
- `request_id`, `session_id`, `task_id` are mandatory
- Raw file contents must not be logged
- Paths and hashes are logged, but sensitive body text is excluded

### 14.3 Health Checks

- Model availability
- SQLite integrity
- Indexing queue length
- Freshness lag
- Selected folder accessibility

## 15. Test Strategy

`pytest passing` alone is insufficient. Tests are divided into five layers.

### 15.1 Contract Tests

- Location: `tests/contracts/`
- Purpose: Verify Protocol, Dataclass, state transitions, and DDL compatibility
- Completion criteria: All core types can be serialized and deserialized

### 15.2 Unit Tests

- Location: `tests/unit/`
- Targets: `QueryDecomposer`, `EvidenceBuilder`, `Governor`, `FreshnessManager`
- Completion criteria: Cover 90%+ of critical branches including normal and exception cases

### 15.3 Integration Tests

- Location: `tests/integration/`
- Targets: SQLite FTS, vector index, MLXRuntime adapter, file watch pipeline
- Completion criteria: Search and citation consistency guaranteed against a sample corpus

### 15.4 Performance Tests

- Location: `tests/perf/`
- Measured items:
  - TTFT
  - End-to-end latency
  - Index lag
  - Trust recovery time
  - Batch indexing throughput
- Minimum interface examples:
  - `run_query_latency_bench(corpus_dir, queries_path) -> PerfReport`
  - `run_index_recovery_bench(file_path, mutation_count) -> PerfReport`

### 15.5 E2E Tests

- Location: `tests/e2e/`
- Flow:
  - CLI input
  - Search
  - Evidence assembly
  - Generation
  - Citation output
  - Approval-gated draft generation
- Completion criteria: All 5 real user scenarios pass

### 15.6 Architecture Fitness Tests

- Prohibited rules:
  - `tools/` must not directly call `runtime/`
  - `runtime/` must not reference `cli/`
  - `retrieval/` must not reference `draft_export`
- Purpose: Automatically prevent Alliance from breaking layer boundaries during implementation

## 16. Implementation Order and Dependency Graph

### 16.1 Phase 0: Bootstrap

- Configure `pyproject.toml`, linting, type checking, and test runner
- Define `contracts/`, `schema.sql`, and base error codes
- Write `observability/metrics.py` and base event contracts
- Generate a sample corpus and a set of 50 queries
- Completion criteria:
  - Contract tests pass
  - SQLite schema creation succeeds
  - E2E smoke test passes with dummy runtime/dummy retriever

### 16.2 Phase 1: Vertical Slice

The dependency order is as follows.

1. `CLI REPL`
2. `Orchestrator`
3. `QueryDecomposer`
4. `FTS5 + vector index`
5. `EvidenceBuilder`
6. `MLXRuntime`
7. `Citation output`
8. `draft_export approval UX`

Parallelizable scope is limited.

- Parallelizable: `contracts/` and `schema.sql`, `metrics.py` and `approval.py`
- Not parallelizable: Search implementation branches before `QueryDecomposer`, generation format extensions before `EvidenceBuilder`

### 16.3 Phase 2: Stabilization

- Connect Governor to actual sensors
- Optimize incremental indexing based on FSEvents
- Optimize stale citation recovery
- Implement automatic failure mode transitions
- Menu bar UI is an optional task

## 17. Role Separation and Approval Framework

### 17.1 Alliance Responsibilities

- Code authoring
- Test authoring and passing
- Contract violation fixes
- Observability event wiring
- Exception handling path implementation

### 17.2 Human Responsibilities

- Final model quality judgment
- Search accuracy sample set verification
- Approval UX adequacy review
- Re-entry condition activation judgment
- Pre-deployment sign-off

### 17.3 Gate Approvers

| Gate | Approver | Criteria |
|---|---|---|
| Contract gate | Human | Protocol/DDL/error code approval |
| Search gate | Human | Top-5 accuracy confirmed on 50 queries |
| Stability gate | Human | Swap, thermal, degraded policy confirmed |
| Feature gate | Alliance + Human | Human final approval after E2E passes |
| Production use gate | Human | 5-day usage criteria met |

## 18. Quantified Validation Criteria

- Search gate: Top-5 accuracy of 80% or higher on 50 queries against the actual corpus
- Citation gate: Citation miss rate of 5% or lower
- Line mapping errors: Target of 0; shipping is blocked if 1 or more occur
- TTFT: Start within 2 seconds
- Meaningful response start: Within 2.5 seconds
- Index lag: Reflect in search within 60 seconds after a single file modification
- Trust recovery time: Modified files recover to `VALID` citation status within 90 seconds
- Unauthorized state changes: 0
- 5-day production use gate: 5 consecutive days, voluntary use 3 or more times per day

### 18.1 Basis for the Numbers

- BM25 alone or FTS alone is likely to remain at around 55-65% for mixed Korean+code queries.
- Hybrid search without a reranker has a realistic target range of 75-85%.
- Therefore, 80% is adopted as an aggressive but achievable baseline for the MVP without a reranker.

## 19. Re-entry Conditions and Switching Costs

Closing a document and permanently locking it are different things. Decisions are revisited only when the following conditions are met.

### 19.1 Kiwi to MeCab-ko Re-evaluation

- Conditions:
  - 50-query Top-5 accuracy falls below 80%
  - The root cause is confirmed to be Korean analysis quality
- Switching cost:
  - Replace `TokenizerProtocol` implementation
  - Full re-indexing of `chunk_terms_ko`
  - Re-run search regression tests
- Estimated cost: 2-4 days

### 19.2 14B Default Tier Re-evaluation

- Conditions:
  - Search meets the criteria, but generation quality consistently falls short
  - Upper tier can be used without degrading battery/memory coexistence
- Switching cost:
  - Re-measure `ModelRouter`, model load policies, and performance tests
- Estimated cost: 2-3 days

### 19.3 Reranker Introduction

- Conditions:
  - Hybrid search falls below 80%, or long-tail query failures are frequent
- Switching cost:
  - Add a re-ranking stage after `HybridSearch`
  - Readjust performance tests
- Estimated cost: 3-5 days

## 20. Halt Criteria, Fallback Criteria, and Plan B

### 20.1 Halt Criteria

- 50-query search accuracy below 70%
- Citation miss rate exceeds 10%
- Repeated swap occurs during concurrent work
- Voluntary use falls below 3 times per day during the 5-day production use period
- User repeatedly requests feature deactivation due to thermal/battery issues

### 20.2 Fallback Criteria

- If model load failures repeat: fall back to search-only mode
- If `draft_export` errors repeat: disable write functionality and output draft text only
- If index corruption repeats: halt incremental indexing and fall back to manual re-indexing mode

### 20.3 Plan B

- Search quality shortfall:
  - Adjust query decomposition rules
  - Correct chunking strategy
  - Introduce a reranker
- MLX compatibility issues:
  - Add a llama.cpp adapter while maintaining `RuntimeProtocol`
- Freshness failures:
  - Inspect FSEvents path
  - Strengthen tombstone handling
  - Readjust delay queue priorities

## 21. Colligi2-Based Document Generation Method

This document was organized through Colligi2's collective AI documentation process. The generation method is not single-model summarization but `multi-AI conflict-convergence review`.

The stages applied are as follows.

1. The original request was redefined as an actionable implementation problem.
2. Each AI independently drafted from the perspectives of architecture, search, Korean processing, security, and local operations.
3. Conflict points between drafts were compared to separate open comparison items from decision gaps.
4. In the review stage, re-evaluation was conducted based on implementability, risk, testing, failure criteria, and operational reliability.
5. In the final stage, rather than averaging compromises, the integration preserved `decisions with stronger evidence` and `dissenting opinions worth retaining`.

Therefore, this document is not a simple summary, but a collectively validated execution document from Colligi2's Implementation Specification for Alliance Coding Directives, designed for Alliance to actually begin implementation.

## 22. Final Recommendation

As Colligi2's Implementation Specification for Alliance Coding Directives, JARVIS is viable to proceed. However, the starting point should not be "can we run a bigger model locally?" but rather "can it explain my documents and code with evidence, avoid harming system resources, and present a draft and impact scope before making changes?"

The items to implement immediately are summarized in a single sentence:

`A local-first workspace agent that searches code and documents in Korean, answers based on a verified evidence set, and exports only approved drafts with limited scope`

If this scope is not achieved, all extended features are deprioritized. Conversely, if this scope is achieved, voice, screen context, and app integration can be evaluated afterward without being too late.

Copyright 2026 Colligi2 | Implementation Specification for Alliance Coding Directives

---

## Document Information

### Participating AIs

| AI | Type | Model |
|------|------|------|
| **claude** | claude_cli | opus |
| **gemini** | gemini_cli | auto |
| **ollama** | ollama | qwen3:30b-a3b |
| **codex** | codex_cli | gpt-5.4 |

> Copyright 2026 Colligi2 | Implementation Specification for Alliance Coding Directives
>
> This document was generated by the AI Collective Intelligence Analysis System (Colligi) on 2026-03-16 23:01.
