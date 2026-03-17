# Project - JARVIS Project

**Document type**: Technical Architecture Document
**Company**: Colligi2
**Project**: JARVIS Project
**Version**: 1.0
**Date**: 2026-03-16

---

## 1. Document Purpose and Decision Summary

This document is a technical execution document that defines the execution architecture of a local AI assistant that can be realistically designed and implemented on a MacBook Pro 16 / Apple M1 Max / 64GB memory environment, for the `JARVIS Project` pursued as the Company's Project. Its purpose goes beyond feasibility assessment to provide decision criteria that specify what scope should be implemented first and what should be deferred.

The key conclusions are as follows:

- This project has a high probability of failure if approached as an `Iron Man-style general-purpose autonomous assistant`, but is entirely feasible if redefined as a `local-first personal workspace agent`.
- The essence of success lies not in model size competition but in `search quality`, `orchestration`, `permission trust`, and `system coexistence`.
- On the M1 Max 64GB environment, a `14B-class` model is realistic as the default resident model, while `~30B models` should be treated as a promotion tier for deep reasoning rather than always-on.
- The MVP should be limited to `text-centric`, `selected-folder-based`, `read + citation + draft generation`.
- Voice, screen recognition, accessibility-based UI automation, and general shell autonomous execution should not be included before initial value validation.
- The acceptance criterion for this document is not "a working demo" but `whether it is voluntarily used 3+ times per day for 5 consecutive days during actual work`.

## 2. Problem Redefinition

The initial question was "Can I build a JARVIS-like local AI assistant on a personal laptop?", but from an execution perspective, the more accurate question is:

`Within the constraints of a personal laptop, can we build a local-first workspace agent that reliably performs Korean Q&A, local search, and task draft generation, and connects the user's documents, code, and task context with supporting evidence?`

Under this redefinition, there are three assumptions that must first be proven with code:

1. Whether Korean search achieves sufficient accuracy on actual personal documents and code corpora
2. Whether the runtime orchestrator can control memory pressure, battery, thermal throttling, and background indexing
3. Whether the minimum vertical slice provides enough trust and convenience to be reused in actual work

This project is closer to `building the foundation of a personal knowledge operating system` than chatbot development. Therefore, `search infrastructure`, `permission policies`, `failure modes`, and `operational policies` matter more than the language model itself.

## 3. Final Product Definition

The primary product definition for the JARVIS Project is:

`A local-first personal AI system that understands the context of my documents and code in Korean, cites supporting evidence, presents drafts before actual execution, and assists only within approved boundaries`

According to this definition, the primary product includes:

- Selected folder indexing
- Unified document and code search
- Evidence-cited Q&A
- Task draft generation
- Conversation history and task context accumulation
- Approval-gated limited execution

According to this definition, the primary product excludes:

- Unrestricted file access
- Accessibility-permission-based general UI manipulation
- General shell autonomous execution
- Always-on voice standby
- Continuous full-screen context capture
- "Do everything automatically" fully autonomous agent

## 4. Hardware Reality and Design Implications

The Apple M1 Max 64GB is a very favorable device for local AI execution, but design decisions must be based on real concurrent usage environments rather than benchmarks.

### 4.1 Hardware Characteristics
- 64GB unified memory
- Memory bandwidth of approximately `200GB/s`
- Apple Silicon architecture where CPU, GPU, and memory pool are shared
- Real usage involves memory competition with IDE, browser, Docker, design tools, and messaging apps

### 4.2 Design Implications
- "The model loads" and "it's usable during daily work" are different things.
- Setting 30B+ models as the default is likely to cause swap, memory pressure, and app-switching delays.
- Increased SSD swap degrades performance and incurs long-term write amplification costs.
- Battery mode requires separate policies for inference and indexing.
- Therefore, the differentiator of this project is not large model deployment but `context-aware control policies`.

## 5. Architecture Principles

The core principles of this project are:

- `Local-first`: Default processing is performed locally, and external dependencies are separated by policy.
- `Search-first`: Search quality is secured before generation quality.
- `Evidence-first`: Factual responses must always be accompanied by sources.
- `Least privilege`: Permissions are opened later than features.
- `Approval-by-default`: State-changing operations are not executed without user approval.
- `Coexistence-first`: The laptop is not an AI-dedicated machine, so it must coexist with work applications.
- `Measurement-based`: All key decisions have metrics and failure criteria.
- `Validate before expanding`: Voice, screen, and automation are expanded only after MVP value is proven.

## 6. Architecture Decision Matrix

| Category | Adopted | Deferred | Experimental | Excluded |
|---|---|---|---|---|
| Product scope | Local-first workspace agent | Fully autonomous personal assistant | Limited remote fallback | General-purpose OS control agent |
| Default interface | CLI REPL, then menu bar UI | Desktop full app | Raycast extension | Voice-first UI |
| LLM runtime | MLX-first | Single engine lock-in | llama.cpp compatibility layer | Server-grade vLLM assumption |
| Generation model strategy | 14B-class default + upper model promotion | Specific single model confirmed | Qwen3-14B, EXAONE Deep 7.8B, Kanana-2-30B-A3B comparison | 30B+ always resident |
| Search architecture | SQLite FTS5 + vector DB + hybrid search + RRF | Vector-only | Cross-encoder reranker | Keyword-only |
| Embeddings | BGE-M3 family as primary candidate | Multilingual general model lock-in | Korean-specialized embedding comparison | No embeddings |
| Korean analysis | Kiwi or MeCab-ko as primary comparison | konlpy abstract wrapper only | Nori-family server-based testing | No Korean morphological processing |
| Indexing | Selected folders + FSEvents incremental indexing | Full disk indexing | Per-app connectors | Manual full reindex only |
| Security | Mandatory citation, approval gate, permission ladder | Full Disk Access as default requirement | Session-scoped temporary permissions | Unrestricted shell execution |
| Automation | Read-only + draft-first | Finder/Mail limited integration | App Intents, Apple Events | Accessibility-based general UI automation |
| Multimodal | Text-first | Always-on voice standby | OCR-based screen context | Continuous screen capture |

## 7. Layered Architecture

The final structure uses a 4-layer frame for stakeholder communication, while the internal implementation is more granular.

### 7.1 Top 4 Layers
1. `Interface Layer`
   - CLI REPL
   - Menu bar UI
   - Approve/reject, status display, citation display

2. `Orchestration Layer`
   - Intent classification
   - Model routing
   - Permission state management
   - Safety policy enforcement
   - Performance control

3. `Knowledge Layer`
   - File collection
   - Chunking
   - FTS index
   - Vector index
   - Conversation and task memory
   - Freshness verification

4. `Model Runtime Layer`
   - Generation model
   - Embedding model
   - Reranking model
   - Inference engine

### 7.2 Detailed Components
| Layer | Component | Role |
|---|---|---|
| Interface | CLI, menu bar, approval panel | Query, response, source display, execution approval |
| Orchestration | Governor, Planner, ToolRegistry | Model promotion, context limits, tool call control |
| Knowledge | Parser, Chunker, FTS5, Vector DB, Metadata Store | Search, freshness, file-symbol-document mapping |
| Memory | Conversation Store, Task Log | Long-term context and recurring task pattern accumulation |
| Runtime | MLX, embedding engine, reranker | Generation and search quality assurance |
| System Bridge | FileManager, Apple Events, limited App Intents | macOS integration |
| Observability | Metrics, Tracing, Failure Log | Performance, error, and regression tracking |

## 8. Data Flow and Control Flow

### 8.1 Q&A Flow
1. The user enters a Korean-language query.
2. The orchestrator determines the query type.
3. The Retriever executes FTS and vector search in parallel.
4. The Freshness Checker verifies whether results are stale.
5. The Context Assembler combines top evidence with conversation context.
6. The Governor determines the model tier based on current memory, battery, and thermal state.
7. The generation model produces a draft answer.
8. The Citation Enforcer detects and corrects unsupported statements.
9. The interface displays the answer along with file paths, chunk evidence, and confidence badges.

### 8.2 Approval-Gated Task Flow
1. The user makes a request such as "organize this", "create a draft", or "move this file".
2. The system does not execute immediately but first presents the `plan` and `impact scope`.
3. Upon user approval, only permitted tools are executed.
4. Execution results are saved along with logs and rollback information.
5. Writes, deletions, or external transmissions without approval are prohibited.

## 9. Key Technology Choices and Selection Criteria

### 9.1 Generation Model Strategy
No specific model is finalized at this point. Instead, the following candidates are designated as Phase 0 benchmark targets:

- `Qwen3-14B` family
- `EXAONE Deep 7.8B` family
- `Kanana-2-30B-A3B` family or equivalent Korean-strong models

The selection criteria are:

- Korean explanation quality
- Code comprehension and modification instruction compliance
- Citation-based answer consistency
- TTFT and tokens/sec
- Memory footprint and swap induction level
- Long-session stability

The decision principles are:

- The default model should be `a model that achieves practical quality at 14B-class or below`
- Upper models are `used only for explicit promotion or complex reasoning scenarios`
- Even if ~30B models show significant advantages in Korean quality, always-on residency is prohibited
- Runtime interfaces are standardized to reduce model switching costs

### 9.2 Runtime
- `MLX` is adopted as the primary choice.
- The rationale is Apple Silicon optimization, memory efficiency, and local deployment simplicity.
- However, if model compatibility issues arise, `llama.cpp` is maintained as a fallback path.
- Therefore, the decision is `MLX-first, llama.cpp compatibility ensured`.

### 9.3 Search
- `SQLite FTS5 + vector DB + hybrid search + RRF` is adopted.
- The rationale is that code identifiers, file names, error messages, and Korean natural language queries cannot be resolved by a single search method.
- Vector-only is weak at codebase and identifier search; FTS-only is weak at semantic similarity search.
- A reranker is not mandatory in Phase 1; it will be added in Phase 2 if search accuracy falls short.

### 9.4 Korean Morphological Processing
Candidates are evaluated along two axes:

- `Kiwi`
  - Pros: Easy Python integration with low installation overhead.
  - Cons: May require custom dictionary tuning for some domain tokens.

- `MeCab-ko`
  - Pros: Traditionally stable with proven morphological analysis quality.
  - Cons: High macOS installation/deployment complexity with potential development environment variance.

The initial policy is:

- MVP default is `Kiwi-first`
- If Korean search accuracy falls short of targets, the `MeCab-ko` path is activated
- Code symbols, file names, and error strings maintain a separate `raw token preservation` index independent of morphological analysis

## 10. Permission and Security Design

Security in this project must be a product structure, not a declaration. macOS TCC is not an inconvenient obstacle but a core UX through which users judge trust.

### 10.1 Permission Ladder
1. `Permission Level 0`
   - Process only manually entered text
   - No indexing
   - Value demonstration demo

2. `Selected Folder Level`
   - Read-only access to user-designated folders
   - Document and code search enabled
   - MVP default level

3. `Limited Write Level`
   - Draft file creation, temporary folder output
   - Requires approval

4. `Advanced Automation Level`
   - Limited integration via Apple Events or App Intents
   - Requires separate configuration and risk disclosure

5. `Accessibility Level`
   - General UI automation
   - Excluded from MVP and initial production scope

### 10.2 Safety Policies
- Factual responses display file paths and chunk evidence.
- Unsupported assertions display confidence warnings.
- Deletion, moving, execution, and external transmission are prohibited by default.
- State-changing operations without an approval token are blocked.
- Hard Kill must trigger immediately on abnormal loops, repeated failures, or excessive file access.

### 10.3 Hard Kill and Failure Blocking
- If a model response is classified as a destructive command, the execution path is blocked
- Tool calls are suspended when consecutive error thresholds are exceeded
- The indexer backs off when causing excessive CPU or disk writes
- All automation features are disabled upon detecting automation regression after a macOS update

## 11. Data Lifecycle and Freshness Management

The most dangerous failure in a local RAG system is "a plausible answer based on stale evidence." Therefore, indexing prioritizes `cleanup and freshness` over collection.

### 11.1 Collection Principles
- Only user-designated folders are indexed
- Separate parsers by file type
- Documents, Markdown, code, logs, and note files prioritized
- Large binary files excluded by default

### 11.2 Freshness Policy
- FSEvents-based incremental indexing
- File modification triggers metadata change propagation first
- Embedding regeneration is processed via a deferred queue
- Recently modified files receive a freshness score boost in search results
- Deleted files are tombstoned then purged from the index

### 11.3 Storage Cost Control
- Large storage is subject to exclusion rules based on file size and change frequency
- Upper limit set for embedding regeneration frequency
- Conversation logs are not permanently stored in full; they are split into a summary tier and a raw tier
- SSD write volume and index growth are recorded on a weekly basis

## 12. Performance, Battery, and Thermal Management Policy

The energy perspective raised in the Gemini draft must be included. In this project, fan noise, battery drain, and heat are not merely performance issues but adoption issues.

### 12.1 Governor Policy
The Governor continuously monitors the following metrics:

- Memory pressure
- Swap usage
- CPU/GPU utilization
- Thermal state
- Power connection status
- Battery level
- Indexing queue length

### 12.2 Mode-Specific Policies
- `Plugged in + Idle`
  - Upper model promotion allowed
  - Aggressive embedding regeneration

- `Plugged in + Active work`
  - Default 14B maintained
  - Indexing runs at low priority

- `Battery mode`
  - Upper model promotion prohibited in principle
  - Indexing paused or reduced
  - Long context responses limited

- `High thermal/high pressure mode`
  - Context size reduced
  - Model unloaded
  - Responsiveness and system stability prioritized over answer quality

### 12.3 Recommended Threshold Policies
Exact values will be calibrated after initial measurements, but the starting policies are:

- If swap occurs significantly, upper model promotion is immediately prohibited
- Indexing backs off when thermal state rises
- Long reasoning is blocked below 30% battery
- Context and search result count are reduced when first-token latency exceeds the threshold

## 13. Risks, Impact, and Response Costs

| Risk | Impact | Likelihood | Cost if wrong | Response |
|---|---|---|---|---|
| Korean search accuracy shortfall | Very high | High | Architecture rework 2-4 weeks | Morphological processor swap, reranker introduction, corpus-specific tuning |
| Memory pressure from always-on 30B strategy | High | High | Performance regression and user abandonment | 14B default, upper model promotion limits |
| Incorrect answers from stale index | Very high | Medium | Trust collapse, difficult root cause analysis | Freshness check, tombstone, reindex policy |
| Excessive permission requirements | High | Medium | Adoption halt, security distrust | Permission ladder, selected folders as default |
| Battery/thermal complaints | High | High | Long-term usage decline | Battery mode policy, indexing backoff |
| macOS automation regression | Medium | Medium | Feature outage 1-2 weeks | Automation deprioritized, feature flags |
| Model quality below expectations | High | Medium | Model re-benchmark 1-2 weeks | Candidate comparison, routing or fallback |
| Index storage growth | Medium | Medium | SSD usage increase, maintenance cost rise | Exclusion rules, compression, summary archival |

## 14. Failure Criteria, Stop Criteria, and Plan B

A senior-level document should include not only "reasons to continue" but also "criteria to stop."

### 14.1 Failure Criteria
- Top-5 accuracy below 80% on 50 queries against actual corpora
- Citation omission rate exceeding 5% in factual answers
- Repeated memory pressure degradation during concurrent work
- Falling short of voluntary usage criteria in a 5-day usage experiment
- Recurring battery mode complaints

### 14.2 Stop Criteria
- When demands for automation feature expansion dominate without search trust being established
- When the least-privilege structure can no longer be maintained
- When excessive external service dependency is required for model quality improvement
- When implementation complexity grows faster than user value

### 14.3 Plan B
- `If 14B quality is insufficient`:
  - Re-evaluate candidates 2 and 3
  - Consider Korean-specialized model routing
  - Re-measure after improving search quality

- `If FTS + vector hybrid underperforms`:
  - Adjust chunking strategy
  - Introduce reranker
  - Separate indexing rules by corpus type

- `If MLX compatibility issues arise`:
  - Switch to llama.cpp path
  - Maintain upper-layer interfaces

- `If automation stability is insufficient`:
  - Reduce execution features
  - Regress to draft/recommendation mode

## 15. Validation Gates

### 15.1 Technical Gates
1. Search Gate
   - Top-5 accuracy of 80% or above on 50 queries against actual document/code corpora

2. Response Gate
   - First token within 2 seconds
   - Meaningful partial response begins within 2.5 seconds

3. Coexistence Gate
   - System responsiveness maintained during concurrent IDE + browser + general work
   - Repeated swap state prohibited

4. Freshness Gate
   - Modified files reflected in search results within the allowed time

5. Safety Gate
   - Zero state-changing operations without approval

### 15.2 Product Gates
- 5 consecutive days of actual work usage
- 3+ voluntary invocations per day
- Confirmed behavioral shift: "I opened local JARVIS before reaching for an external service"
- Subjective trust increase in citation-based answers

## 16. Execution Roadmap

Weekly plans alone are insufficient, so Day 0 prerequisites and role assumptions are included.

### 16.1 Prerequisites
- Base assumption: 1-person or small core team project
- Required skills: Python, macOS, search/RAG, local model operations
- Primary implementation environment: Local development Python, minimal SwiftUI UI, MLX runtime

### 16.2 Day 0 Checklist
- Lock down development environment
- Standardize model execution method
- Select test corpus
- Write 50 benchmark questions
- Define metrics collection method
- Draft permission policy statement

### 16.3 4-Week Execution Plan
1. `Week 1`
   - Build CLI REPL
   - Connect MLX-based candidate model loader
   - Embed performance instrumentation
   - Complete single conversation loop without search

2. `Week 2`
   - Selected folder indexing
   - Connect FTS5 + vector DB + RRF
   - Implement citation-based responses
   - First measurement against 50-query benchmark

3. `Week 3`
   - Conversation history indexing
   - Freshness checks
   - Approval-gated draft generation
   - Add menu bar UI or approval panel

4. `Week 4`
   - 5-day real-world usage test
   - Correct search failure patterns
   - Calibrate battery/thermal policies
   - Decide whether to proceed to the next phase

### 16.4 Phase Exit Criteria
- Week 1 exit: Model responses and metric collection operational
- Week 2 exit: Citation-included search responses operational
- Week 3 exit: Read + draft + approval flow operational
- Week 4 exit: Able to determine whether real-world usage criteria are met

## 17. Intentional Technical Debt Left in MVP

Technical debt should be budgeted openly rather than hidden, so that future decisions remain clear.

- Phase 1 excludes cross-encoder reranker by default
- Phase 1 prioritizes CLI stability over menu bar UI
- Phase 1 uses conversation logs + summary tier instead of full long-term memory
- Phase 1 focuses on draft generation over automation
- Phase 1 defaults to a single Korean morphological processing path; the alternative path is introduced only if targets are not met

These choices are intentional scope control, not shortcomings.

## 18. Future Expansion Directions

The following are considered only after the MVP is validated:

- Voice input/output
- OCR-based screen context
- Limited app integration
- Multi-device context synchronization
- Selective remote inference with security policies in place
- Personal workflow automation for recurring tasks

The prerequisite for expansion decisions is always the same: `search trust, permission trust, and coexistence` must not be compromised.

## 19. Colligi2-Based Document Generation Method

This document was organized through Colligi2's collective AI documentation process. The generation method is not single-model summarization but `multi-AI conflict-convergence review`.

The stages applied are:

1. Redefining the surface question of the original request into an actionable problem
2. Each AI independently drafting from architecture, performance, security, Korean processing, and local-first perspectives
3. Comparing conflict points between drafts and separating exaggerations, inconsistencies, and omissions
4. Re-evaluating during the review stage with focus on feasibility, risks, validation gates, and failure criteria
5. In the final stage, integrating the document while retaining `decisions with stronger evidence` and `disagreements that should be preserved` rather than averaging compromises

Therefore, this document is not a simple summary but a decision document for the Company, retaining only the choices that increase the Project's execution feasibility from among conflicting proposals.

## 20. Final Recommendations

The JARVIS Project is well worth pursuing as the Company's Project. However, the starting point should not be "Can we run a large model locally?" but rather "Can it present trustworthy evidence about my documents and code without disrupting actual work?"

Recommendations for immediate adoption:

- `14B-class default model + upper model promotion structure`
- `MLX-first, llama.cpp compatibility ensured`
- `SQLite FTS5 + vector DB + hybrid search`
- `Selected-folder-based indexing`
- `Mandatory citation and approval-gated execution`
- `Governor that reflects battery, thermal, and memory state`

Recommendations for immediate prohibition:

- Full Disk Access as default requirement
- Accessibility-permission-based general UI automation
- General shell autonomous execution
- Pre-loading voice/screen features
- Expanding automation scope before search trust is established

The correct primary goal of this project is summarized in one sentence:

`A local-first workspace agent that explains my code and documents in Korean with supporting evidence, and presents drafts and impact scope before executing any requested task`

If this goal is met, JARVIS becomes an extensible system. If not, no amount of flashy features will achieve long-term adoption.

## 21. Document Information

- Company: Company
- Project: Project
- Document title: JARVIS Project
- Version: 1.0
- Target environment: MacBook Pro 16 / Apple M1 Max / 64GB memory
- Generation timestamp: 2026-03-16 Asia/Seoul
- Participating AIs: Claude, Codex, Gemini, Ollama

(C) 2026 Company | Project

## Colligi2 Generation Process

This document is not the result of a single AI writing at once, but a collective intelligence output produced through multiple AIs cross-verifying the same topic in stages.

1. **Intent Reconstruction**: Reconstructed the actual goals, hidden constraints, and questions requiring validation behind the user's surface request.
2. **Stage Design**: Multiple AIs independently proposed analysis stages, and the final analysis structure was designed through research and merging.
3. **Multi-Stage Discussion**: At each analysis stage, AIs exchanged opinions, evaluations, and counterarguments to organize issues and alternatives.
4. **Emergent Integration**: Rather than simply summarizing stage-by-stage results, conflict points and new insights were collectively synthesized.
5. **Problem Redefinition**: Re-examined whether the original question was sufficiently precise and corrected it to a more essential problem definition.
6. **Collective Document Authoring**: After cross-reviewing multiple drafts and reviews, the final document was integrated and edited.

- Number of participating AIs: 4
- Number of final analysis stages: 17
- Total discussion rounds: 24
- Records of providers excluded due to intermediate failures: 0

---

## Document Information

### Participating AIs

| AI | Type | Model |
|------|------|------|
| **claude** | claude_cli | opus |
| **gemini** | gemini_cli | auto |
| **ollama** | ollama | qwen3:30b-a3b |
| **codex** | codex_cli | gpt-5.4 |

> (C) 2026 Colligi2 | JARVIS Project
>
> This document was generated at 2026-03-16 11:33 by the AI Collective Intelligence Analysis System (Colligi).
